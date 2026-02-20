import streamlit as st
import urllib.request
import tarfile
import subprocess
import os
import shutil
import tempfile

def download_and_extract(arxiv_id, version, extract_to):
    url = f"https://arxiv.org/e-print/{arxiv_id}v{version}"
    archive_path = os.path.join(extract_to, f"v{version}.tar.gz")
    
    # Custom User-Agent to comply with arXiv's automated download policies
    req = urllib.request.Request(url, headers={'User-Agent': 'VibeArxivDiff-App'})
    with urllib.request.urlopen(req) as response, open(archive_path, 'wb') as out_file:
        out_file.write(response.read())

    version_dir = os.path.join(extract_to, f"v{version}")
    os.makedirs(version_dir, exist_ok=True)
    
    try:
        with tarfile.open(archive_path) as tar:
            tar.extractall(path=version_dir)
    except tarfile.ReadError:
        # Fallback if arXiv serves a single flat .tex file instead of an archive
        shutil.move(archive_path, os.path.join(version_dir, "main.tex"))
    else:
        os.remove(archive_path)
        
    return version_dir

def find_main_tex(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".tex"):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        if r"\begin{document}" in f.read():
                            return path
                except Exception:
                    continue
    raise FileNotFoundError(f"Could not find a .tex file with \\begin{{document}} in {directory}")

# --- Streamlit UI Setup ---
st.set_page_config(page_title="VibeArxivDiff", page_icon="📄")
st.title("VibeArxivDiff")
st.write("Generate a `latexdiff` PDF between two versions of an arXiv paper. Math markup is disabled to ensure compilation stability.")

# Input fields
arxiv_id = st.text_input("ArXiv ID", value="2510.23513")
col1, col2 = st.columns(2)
with col1:
    v1 = st.text_input("Old Version", value="1")
with col2:
    v2 = st.text_input("New Version", value="2")

if st.button("Generate Diff PDF"):
    if not arxiv_id or not v1 or not v2:
        st.warning("Please fill in all fields.")
    else:
        with st.spinner("Downloading, diffing, and compiling... this usually takes 1-2 minutes."):
            try:
                # Create a sandboxed temporary directory for this specific run
                with tempfile.TemporaryDirectory() as temp_dir:
                    
                    # 1. Download and extract both versions
                    dir_v1 = download_and_extract(arxiv_id, v1, temp_dir)
                    dir_v2 = download_and_extract(arxiv_id, v2, temp_dir)
                    
                    # 2. Locate the main .tex files
                    tex_v1 = find_main_tex(dir_v1)
                    tex_v2 = find_main_tex(dir_v2)
                    
                    # 3. Run latexdiff (writing output to the v2 folder so it has access to the latest figures)
                    diff_tex_path = os.path.join(dir_v2, "diff.tex")
                    with open(diff_tex_path, "w", encoding="utf-8") as f:
                        subprocess.run(
                            ["latexdiff", "--math-markup=0", os.path.abspath(tex_v1), os.path.abspath(tex_v2)], 
                            stdout=f, 
                            cwd=dir_v2,
                            check=True
                        )
                    
                    # 4. Compile the diff.tex using latexmk
                    subprocess.run(
                        ["latexmk", "-pdf", "-f", "-interaction=nonstopmode", "diff.tex"], 
                        cwd=dir_v2,
                        capture_output=True # Suppress the heavy console output in the server logs
                    )
                    
                    final_pdf = os.path.join(dir_v2, "diff.pdf")
                    
                    # 5. Check if the PDF was generated and offer it for download
                    if os.path.exists(final_pdf):
                        # Read bytes into memory before the temp folder is destroyed
                        with open(final_pdf, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()
                            
                        st.success("Compilation successful!")
                        st.download_button(
                            label="Download Diff PDF",
                            data=pdf_bytes,
                            file_name=f"{arxiv_id}_v{v1}_to_v{v2}_diff.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.error("Compilation failed. The LaTeX source might have unresolvable errors or rely on missing packages.")
                        
            except FileNotFoundError as e:
                st.error(str(e))
            except subprocess.CalledProcessError:
                st.error("latexdiff failed to run. Check the file structures.")
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
