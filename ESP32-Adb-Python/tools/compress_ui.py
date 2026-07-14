import gzip
import shutil
import os

# Get path relative to the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
app_html_path = os.path.join(script_dir, '..', 'firmware', 'web', 'app.html')
app_html_gz_path = os.path.join(script_dir, '..', 'firmware', 'web', 'app.html.gz')

print(f"Compressing {app_html_path} to {app_html_gz_path}...")

with open(app_html_path, 'rb') as f_in:
    with gzip.open(app_html_gz_path, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

print("Compression successful!")
