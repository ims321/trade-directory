import subprocess

print("🔑 Paste your Supabase anon (eyJ...) key here and press Enter:")
key = input("> ").strip()

if not key.startswith("eyJ"):
    print("⚠️ Warning: That doesn't look like a valid Supabase anon key.")

with open("docs/app.js", "r") as f:
    content = f.read()

# Replace whatever is currently in the ANON_KEY line with the new key
import re
content = re.sub(r'const ANON_KEY\s*=\s*".*?";', f'const ANON_KEY     = "{key}";', content)

with open("docs/app.js", "w") as f:
    f.write(content)

print("✅ app.js updated with your key.")
print("🚀 Pushing to GitHub...")
subprocess.run(["git", "add", "."])
subprocess.run(["git", "commit", "-m", "Fixed API key for map"])
subprocess.run(["git", "push", "origin", "main"])
print("🎉 Done! Wait 60 seconds, refresh your live site, and it will work.")
