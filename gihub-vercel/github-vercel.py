import streamlit as st
import subprocess
import requests
import os
import re
import zipfile
import tempfile
import shutil

st.set_page_config(page_title="Cloud Auto-Deploy", layout="centered")

st.title("☁️ Cloud to Vercel Deployer")
st.write("Upload your project as a .zip file (up to 1GB), provide your tokens, and deploy directly.")

with st.form("deploy_form"):
    st.write("### 📁 Project Information")
    uploaded_file = st.file_uploader("Upload Project Folder (.zip)", type=["zip"])
    repo_name = st.text_input("Repository / Project Name", placeholder="my-awesome-app")

    st.markdown("---")
    st.write("### 🔑 API Credentials")
    github_username = st.text_input("GitHub Username")
    github_token = st.text_input("GitHub Personal Access Token", type="password")
    vercel_token = st.text_input("Vercel Access Token", type="password")

    submitted = st.form_submit_button("Upload and Deploy")

if submitted:
    if not uploaded_file:
        st.error("Please upload a .zip file of your project.")
        st.stop()
    if not repo_name or not github_username or not github_token or not vercel_token:
        st.error("Please fill in all repository and credential fields.")
        st.stop()

    # Clean repo name for both GitHub and Vercel:
    # Lowercase, collapse spaces/symbols/multiple hyphens into a single '-', cap at 100 chars
    repo_name = re.sub(r"[^a-z0-9]+", "-", repo_name.strip().lower()).strip("-")[:100].strip("-")
    github_username = github_username.strip()

    if not repo_name:
        st.error("Project name must contain at least one letter or number.")
        st.stop()

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Save uploaded ZIP in 8MB chunks to prevent RAM crashes
            st.info("Saving uploaded ZIP file...")
            zip_path = os.path.join(temp_dir, "uploaded_project.zip")
            uploaded_file.seek(0)
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(uploaded_file, f, length=8 * 1024 * 1024)

            # Extract the contents
            st.info("Extracting ZIP file...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Delete the zip file to free up disk space
            os.remove(zip_path)

            # Detect if the ZIP extracted into a single outer folder
            items = [i for i in os.listdir(temp_dir) if i != "__MACOSX"]
            if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
                work_dir = os.path.join(temp_dir, items[0])
            else:
                work_dir = temp_dir

            # Remove heavy build/dependency folders (Vercel rebuilds these automatically)
            ignore_dirs = {"node_modules", ".git", ".next", "dist", "build", "venv", ".venv", "__pycache__"}
            for root, dirs, files in os.walk(work_dir, topdown=True):
                for d in list(dirs):
                    if d in ignore_dirs:
                        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                        dirs.remove(d)

            # Step 1: Create GitHub Repository
            st.info(f"Creating GitHub repository '{repo_name}'...")
            gh_headers = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            gh_res = requests.post(
                "https://api.github.com/user/repos",
                json={"name": repo_name, "private": False},
                headers=gh_headers
            )

            if gh_res.status_code not in [201, 422]:
                st.error(f"GitHub API Error: {gh_res.json().get('message')}")
                st.stop()

            st.success(f"GitHub repository '{repo_name}' is ready.")

            # Step 2: Initialize Git and Push Code
            st.info("Pushing code to GitHub...")
            remote_url = f"https://{github_username}:{github_token}@github.com/{github_username}/{repo_name}.git"

            commands = [
                ["git", "init"],
                ["git", "config", "user.email", "bot@streamlit.app"],
                ["git", "config", "user.name", "Streamlit Cloud Bot"],
                ["git", "add", "."],
                ["git", "commit", "-m", "Automated deployment via Streamlit Cloud"],
                ["git", "branch", "-M", "main"],
                ["git", "remote", "add", "origin", remote_url],
                ["git", "push", "-u", "origin", "main", "--force"]
            ]

            for cmd in commands:
                result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
                if result.returncode != 0:
                    err_msg = result.stderr.replace(github_token, "***")
                    st.error(f"Git error on `{' '.join(cmd[:2])}`:\n{err_msg}")
                    st.stop()

            st.success("Code successfully pushed to GitHub!")

            # Step 3: Vercel Deploy
            st.info("Deploying to Vercel...")
            vc_headers = {"Authorization": f"Bearer {vercel_token}"}
            vc_payload = {
                "name": repo_name,
                "gitRepository": {
                    "type": "github",
                    "repo": f"{github_username}/{repo_name}"
                }
            }

            vc_res = requests.post("https://api.vercel.com/v9/projects", json=vc_payload, headers=vc_headers)

            if vc_res.status_code in [200, 201]:
                project_data = vc_res.json()
                domain = f"{project_data.get('name')}.vercel.app"
                st.success("🎉 Deployment triggered successfully!")
                st.markdown(f"**Your live site will be available at:** [https://{domain}](https://{domain})")
            else:
                st.error(f"Vercel API Error: {vc_res.json().get('error', {}).get('message', 'Unknown error')}")

        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}")