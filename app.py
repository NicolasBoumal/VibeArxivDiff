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
arxiv_id = st.text_input("ArXiv ID", value="2303.00096")
col1, col2 = st.columns(2)
with col1:
    v1 = st.text_input("Old Version", value="1")
with col2:
    v2 = st.text_input("New Version", value="2")

if st.button("Generate Diff PDF"):
    if not arxiv_id or not v1 or not v2:
        st.warning("Please fill in all fields.")
    else:
        with st.status("Processing paper... this usually takes 1-2 minutes.", expanded=True) as status:
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    st.write(f"Downloading v{v1} and v{v2}...")
                    dir_v1 = download_and_extract(arxiv_id, v1, temp_dir)
                    dir_v2 = download_and_extract(arxiv_id, v2, temp_dir)
                    
                    st.write("Locating main .tex files...")
                    tex_v1 = find_main_tex(dir_v1)
                    tex_v2 = find_main_tex(dir_v2)
                    
                    st.write("Running latexdiff...")
                    diff_tex_path = os.path.join(dir_v2, "diff.tex")
                    with open(diff_tex_path, "w", encoding="utf-8") as f:
                        subprocess.run(
                            ["latexdiff", "--math-markup=0", os.path.abspath(tex_v1), os.path.abspath(tex_v2)], 
                            stdout=f, 
                            cwd=dir_v2,
                            check=True
                        )
                    
                    st.write("Compiling PDF...")
                    compile_process = subprocess.run(
                        ["latexmk", "-pdf", "-f", "-interaction=nonstopmode", "diff.tex"], 
                        cwd=dir_v2,
                        capture_output=True, 
                        text=True # Capture output as string for the error log
                    )
                    
                    final_pdf = os.path.join(dir_v2, "diff.pdf")
                    
                    if os.path.exists(final_pdf):
                        with open(final_pdf, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()
                            
                        status.update(label="Compilation successful!", state="complete", expanded=False)
                        st.download_button(
                            label="Download Diff PDF",
                            data=pdf_bytes,
                            file_name=f"{arxiv_id}_v{v1}_to_v{v2}_diff.pdf",
                            mime="application/pdf"
                        )
                    else:
                        status.update(label="Compilation failed.", state="error", expanded=False)
                        st.error("The cloud server is missing a package required by this paper, or latexdiff created unresolvable syntax.")
                        
                        # Escape Hatch: Zip the folder and offer it for download
                        zip_path = shutil.make_archive(dir_v2, 'zip', dir_v2)
                        with open(zip_path, "rb") as zip_file:
                            st.download_button(
                                label="Download Source Files (.zip) to Compile Locally",
                                data=zip_file.read(),
                                file_name=f"{arxiv_id}_v{v1}_to_v{v2}_source.zip",
                                mime="application/zip"
                            )
                            
                        # Surface the error log for debugging
                        with st.expander("View latexmk error log"):
                            st.code(compile_process.stdout, language="text")
                            
            except FileNotFoundError as e:
                status.update(label="Error locating files.", state="error")
                st.error(str(e))
            except subprocess.CalledProcessError:
                status.update(label="latexdiff error.", state="error")
                st.error("latexdiff failed to run. Check the file structures.")
            except Exception as e:
                status.update(label="Unexpected error.", state="error")
                st.error(f"An unexpected error occurred: {e}")