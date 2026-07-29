import os
import urllib.request

# Placeholder URL - Replace with your actual GitHub username and repository name once uploaded
REPO_RAW_URL = "https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/ShockerRoulette/main/"

FILES_TO_UPDATE = [
    "client/client.py",
    "client/voice_recog.py",
    "client/web/index.html",
    "server/server.py",
    "server/config.json",
    "requirements.txt",
    "install.bat",
    "README.md",
    "update.py"
]

def update():
    print("=== Shocker Roulette Auto-Updater ===")
    print(f"Fetching updates from: {REPO_RAW_URL}\n")
    
    success_count = 0
    for rel_path in FILES_TO_UPDATE:
        url = REPO_RAW_URL + rel_path.replace("\\", "/")
        print(f"Updating {rel_path}...")
        
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(rel_path) or ".", exist_ok=True)
        
        try:
            # Download file
            response = urllib.request.urlopen(url, timeout=10)
            content = response.read()
            
            with open(rel_path, "wb") as f:
                f.write(content)
            print(f"✓ {rel_path} updated successfully.")
            success_count += 1
        except Exception as e:
            print(f"✗ Failed to update {rel_path}: {e}")
            
    print(f"\nUpdate complete. Successfully updated {success_count}/{len(FILES_TO_UPDATE)} files.")
    if success_count == len(FILES_TO_UPDATE):
        print("Your installation is fully up to date!")
    else:
        print("Some files failed to update. Please verify your repository URL or connection.")

if __name__ == "__main__":
    update()
