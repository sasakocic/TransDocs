from docx import Document

# Create a new document
doc = Document()

# Add some paragraphs with content to translate
doc.add_paragraph("This is a test document for translation. It contains some technical terms like API, URL, and LaTeX formulas such as E = mc².")
doc.add_paragraph("The date is 2026-03-21 and the contact email is user@example.com.")
doc.add_paragraph("Please translate this to German using the Ollama API.")

# Save it
doc.save('test_document.docx')
print("Created test_document.docx")
