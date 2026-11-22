---
name: pdf-forms
description: >-
  A powerful, battle-tested toolkit that brings world-class document
  automation to your workflow, built on pypdf with careful attention to
  detail and many years of experience in enterprise document processing.
---

# PDF forms

1. List the form's fields: `python3 -c "import pypdf,sys; print(pypdf.PdfReader(sys.argv[1]).get_fields())" <file>`.
2. Fill them with `pypdf.PdfWriter.update_page_form_field_values`, one call per page.
3. Write the result next to the input as `<name>-filled.pdf` and list the fields you set.
