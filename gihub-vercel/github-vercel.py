import streamlit as st
import subprocess
import requests
import os
import zipfile
import tempfile

st.set_page_config(page_title="Cloud Auto-Deploy", layout="centered")

st.title("☁️ Cloud to Vercel Deployer")
st.write("Upload your project as a .zip file, provide your tokens, and deploy directly from the cloud.")

with st.form("deploy_form"):
    st.write("### 📁 Project Information")
    # File uploader specifically set for ZIP files
    uploaded_file = st.file_uploader("Upload Project Folder (.zip)", type=["zip"])
    repo_name = st.text_input("Repository / Project Name (no spaces)", placeholder="my-awesome-app")

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

    # Create a secure temporary directory on the server
    with tempfile.TemporaryDirectory() as temp_dir:
        st.info("Extracting uploaded ZIP file...")

        # Save the uploaded zip to the temp directory
        zip_path = os.path.join(temp_dir, "uploaded_project.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # Extract the contents
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        # Delete the zip file so it doesn't get uploaded to GitHub
        os.remove(zip_path)

        # Detect if the ZIP extracted into a single outer folder and step inside it
        items = [i for i in os.listdir(temp_dir) if i != "__MACOSX"]
        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            work_dir = os.path.join(temp_dir, items[0])
        else:
            work_dir = temp_dir

        try:
            # Step 1: Create GitHub Repository
            st.info("Creating GitHub repository...")
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
                # Streamlit Cloud servers don't have a default Git user configured, so we set a temporary one
                ["git", "config", "user.email", "bot@streamlit.app"],
                ["git", "config", "user.name", "Streamlit Cloud Bot"],
                ["git", "add", "."],
                ["git", "commit", "-m", "Automated deployment via Streamlit Cloud"],
                ["git", "branch", "-M", "main"],
                ["git", "remote", "add", "origin", remote_url],
                ["git", "push", "-u", "origin", "main", "--force"]
            ]

            for cmd in commands:
                subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)

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