from docx import Document

doc = Document('output_proofread.docx')
print("Proofread document content:")
for para in doc.paragraphs:
    print(para.text)
