with open("scripts/compile_pageoph_package.py", "r", encoding="utf-8") as f:
    text = f.read()

# Add def set_row_header
old_def = """def set_row_cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    cantSplit = parse_xml(f'<w:cantSplit {nsdecls("w")}/>')
    trPr.append(cantSplit)"""

new_def = """def set_row_cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    cantSplit = parse_xml(f'<w:cantSplit {nsdecls("w")}/>')
    trPr.append(cantSplit)

def set_row_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = parse_xml(f'<w:tblHeader {nsdecls("w")}/>')
    trPr.append(tblHeader)"""

if "def set_row_header" not in text:
    text = text.replace(old_def, new_def)

# Add set_row_header call
old_call = """        for i, row in enumerate(rows):
            set_row_cant_split(table.rows[i])"""

new_call = """        for i, row in enumerate(rows):
            set_row_cant_split(table.rows[i])
            if i == 0:
                set_row_header(table.rows[i])"""

if "set_row_header(table.rows[i])" not in text:
    text = text.replace(old_call, new_call)

with open("scripts/compile_pageoph_package.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Updated compile_pageoph_package.py successfully.")
