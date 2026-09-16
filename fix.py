import re
import os

files = [
    'frontend/src/routes/_authenticated.analyze.tsx',
    'frontend/src/routes/_authenticated.dashboard.tsx',
    'frontend/src/routes/_authenticated.doctors.tsx',
    'frontend/src/routes/_authenticated.history.tsx',
    'frontend/src/routes/_authenticated.profile.tsx',
    'frontend/src/routes/_authenticated.results.$id.tsx',
    'frontend/src/routes/_authenticated.settings.tsx'
]

for f in files:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Remove import
        content = re.sub(r'import\s*\{\s*AppShell\s*\}\s*from\s*["\']@/components/app-shell["\'];?\s*\n', '', content)
        
        # Replace JSX tags with fragments
        content = content.replace('<AppShell>', '<>')
        content = content.replace('</AppShell>', '</>')
        
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Updated {f}")
