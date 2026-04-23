import docx
import json

def get_docx_structure(filepath):
    doc = docx.Document(filepath)
    structure = []
    
    for i, para in enumerate(doc.paragraphs):
        if para.style.name.startswith('Heading') or para.text.strip():
            structure.append({
                'index': i,
                'style': para.style.name,
                'text': para.text.strip()[:100] + ('...' if len(para.text.strip()) > 100 else '')
            })
            
    with open('docx_structure.json', 'w', encoding='utf-8') as f:
        json.dump(structure, f, indent=4)

get_docx_structure('c:\\Users\\DELL\\Desktop\\code_playground\\Priyanshi project\\docus\\final LipReading_Project_Report.docx')
