import subprocess
import re

print("🔑 Paste your Supabase anon (eyJ...) key here and press Enter (or press Enter to keep the existing key):")
key = input("> ").strip()

if key: # Only update if a key was provided
    with open("docs/app.js", "r") as f:
        content = f.read()
    content = re.sub(r'const ANON_KEY\s*=\s*".*?";', f'const ANON_KEY     = "{key}";', content)
    with open("docs/app.js", "w") as f:
        f.write(content)
    print("✅ Key updated.")

print("🚀 Pushing to GitHub...")
subprocess.run(["git", "add", "."])
subprocess.run(["git", "commit", "-m", "Fixed role filter event listeners"])
subprocess.run(["git", "push", "origin", "main"])
print("🎉 Done! Refresh your live site.")
