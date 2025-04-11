from pathlib import Path
import markdown
from md_mermaid import MermaidExtension
import sys
from mermaid_extension import MermaidExtension as mermaid_ext

def convert_md_to_html(md_file_path, output_folder):
    # Read the Markdown file
    with open(md_file_path, "r", encoding="utf-8") as md_file:
        md_content = md_file.read()

    # Initialize the Markdown object with the extensions
    md = markdown.Markdown(extensions=[
        # MermaidExtension(),  # Proper initialization of MermaidExtension
        mermaid_ext(),
        'fenced_code',
        'codehilite',
        'tables',
        'toc'
    ])

    md_content = convert_hyperlink_to_html(md_content)
    # Convert Markdown to HTML
    html_content = md.convert(md_content)
    
    # wrap the HTML content in a basic HTML structure
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{md_file_path}</title>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true }});
        </script>
       <style>
            body {{
                max-width: 800px;
                margin: 2em auto;
                font-family: system-ui, sans-serif;
                line-height: 1.6;
                color: #333;
                padding: 0 1em;
            }}
            pre {{
                background: #f6f8fa;
                padding: 1em;
                overflow-x: auto;
            }}
            code {{
                background: #f0f0f0;
                padding: 2px 4px;
                border-radius: 4px;
            }}
            a {{
                color: #0366d6;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
</head>
<body>
{html_content}
</body>
</html>
"""   

    # create the output file path
    output_file_path = output_folder / md_file_path.relative_to(md_file_path.parent).with_suffix(".html")
    
    # write the HTML content to a file
    with open(output_file_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)
        
    print(f"Converted {md_file_path} to {output_file_path}")
    

def convert_hyperlink_to_html(md_content):
    # replace any hyperlinks with HTML links (.md to .html)
    md_content = md_content.replace(".md", ".html")
    return md_content
    
def convert_all_md_to_html(md_folder_path, output_folder=None):
    md_folder_path = Path(md_folder_path)
    output_folder = Path(output_folder) if output_folder else md_folder_path / "html"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # iterate through all Markdown files in the folder
    for md_file in md_folder_path.glob("**/*.md"):
        convert_md_to_html(md_file, output_folder)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python md_to_html.py <md_folder_path> <output_folder>")
        sys.exit(1)
    else:
        md_folder_path = sys.argv[1]
        output_folder = sys.argv[2] if len(sys.argv) > 2 else None
        convert_all_md_to_html(md_folder_path, output_folder)