import sys,os
sys.stdout.reconfigure(encoding="utf-8")
def main():
    lines=[]
    lines.append("# EPI-Recorder V4.2.0 -- Complete Technical Documentation")
    lines.append("")
    with open(os.path.join(os.path.expanduser("~"),"epi-recorder","DOCUMENTATION_V4.2.0.md"),"w",encoding="utf-8") as f:
        f.write(chr(10).join(lines))
    print("Written")
main()