import os
path = os.path.expandvars(r'C:\Users\dell\epi-recorder\epi_cli\annex.py')
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old = 'EPIContainer.pack(sd,smn,out,preserve_generated=True,generate_analysis=False,container_format="legacy-zip")'
new = '''EPIContainer.pack(sd,smn,out,preserve_generated=True,generate_analysis=False,container_format="legacy-zip")
    try:
        m2 = ManifestModel(**EPIContainer.unpack(out)["manifest"])
        s2 = sign_manifest(m2, pk, key_name)
        EPIContainer.pack(sd, s2, out, preserve_generated=True, generate_analysis=False, container_format="legacy-zip")
    except Exception:
        pass'''

if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print("PATCHED")
else:
    print("NOT FOUND at byte", c.find('EPIContainer.pack(sd,smn'))
    # show what's actually there
    i = c.find('EPIContainer.pack')
    if i > -1:
        print(repr(c[i:i+200]))
