from docx import Document

doc = Document('output.docx')
print("Translated document content:")
for para in doc.paragraphs:
    print(para.text)
