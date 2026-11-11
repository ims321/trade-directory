import subprocess
import re

print("🔑 Paste your Supabase anon (eyJ...) key here and press Enter:")
key = input("> ").strip()

with open("docs/app.js", "r") as f:
    content = f.read()

content = re.sub(r'const ANON_KEY\s*=\s*".*?";', f'const ANON_KEY     = "{key}";', content)

with open("docs/app.js", "w") as f:
    f.write(content)

print("✅ Key updated. Pushing to GitHub...")
subprocess.run(["git", "add", "."])
subprocess.run(["git", "commit", "-m", "Loaded 7300 global companies and added role filter"])
subprocess.run(["git", "push", "origin", "main"])
print("🎉 Done! Wait 60 seconds, refresh your live site, and enjoy.")
