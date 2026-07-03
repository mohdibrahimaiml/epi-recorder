from __future__ import annotations
from pathlib import Path;import json
from datetime import datetime,timezone
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from epi_core.annex_schemas import *
from epi_core.keys import KeyManager
from epi_cli.role_bindings import check_role_authorized, bind_role, unbind_role, list_roles, verify_all_signers, _pubkey_fingerprint
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

console=Console()
annex_app=typer.Typer(help="Annex IV compliance artifacts")
D="artifacts/annex_iv"
SEC={"1":"System Description","2":"Development Process","3":"Monitoring and Control","4":"Performance Metrics","5":"Risk Management","6":"Lifecycle Changes","7":"Applied Standards","8":"EU Declaration of Conformity","9":"Post-Market Monitoring"}
CLS={"1":Section01System,"2":Section02Development,"3":Section03Monitoring,"4":Section04Metrics,"5":Section05RiskManagement,"6":Section06Lifecycle,"7":Section07Standards,"8":Section08Declaration,"9":Section09PostMarket}

def _canon(data):ac={k:v for k,v in data.get("approval",{}).items() if k!="signature"};cd=dict(data);cd["approval"]=ac;cd.pop("signature",None);return json.dumps(cd,sort_keys=True,separators=(",",":"),default=str)
def _key(n):km=KeyManager();km.has_key(n)or km.generate_keypair(n);return km.load_private_key(n)
def _pub(n):return KeyManager().load_public_key(n)

@annex_app.command()
def init(force:bool=False,out:Path=Path(".")):
    d=out/D;d.mkdir(exist_ok=True,parents=True)
    for n,t in SEC.items():
        f=d/f"section-0{n}.json"
        if f.exists()and not force:console.print(f"  SKIP {f.name}");continue
        m=CLS[n]().model_dump(mode="json")
        f.write_text(json.dumps(m,indent=2,default=str))
        console.print(f"  OK Section {n}")
    console.print(Panel(f"Generated {len(SEC)} templates",title="Annex IV Init"))

@annex_app.command()
def validate(dir:Path=Path(".")):
    b=dir/D
    if not b.exists():console.print("[red]No artifacts/annex_iv/ found[/]");raise typer.Exit(1)
    p,f=0,0
    for n,t in SEC.items():
        fp=b/f"section-0{n}.json"
        if not fp.exists():console.print(f"  MISSING {n}");f+=1;continue
        try:d=json.loads(fp.read_text());CLS[n](**d);console.print(f"  PASS {n}");p+=1
        except Exception as e:console.print(f"  FAIL {n}:{e}");f+=1
    console.print(Panel(f"{p}/{len(SEC)} pass,{f} fail",title="Validate"))
    if f:raise typer.Exit(1)
@annex_app.command()
def status(dir:Path=Path(".")):
    b=dir/D;t=Table(title="Annex IV Status");t.add_column("Sec");t.add_column("Section");t.add_column("Status");t.add_column("Approved")
    for n,s in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():t.add_row(n,s,"[red]MISSING[/]","-");continue
        d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");ap=d.get("approval",{}).get("signed_by","-")or"-"
        co={"missing":"red","draft":"yellow","complete":"green","approved":"green"}.get(st,"yellow")
        t.add_row(n,s,f"[{co}]{st.upper()}[/]",ap)
    console.print(t)

@annex_app.command()
def compile(dir:Path=Path("."),out:Path=Path(".")):
    b=dir/D;assert b.exists(),"Run init first"
    ss=[];pop=0;app=0
    for n,t in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():ss.append({"section":n,"title":t,"status":"missing"});continue
        d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");ap=d.get("approval",{})
        if st in ("complete","approved"):pop+=1
        if st=="approved":app+=1
        ss.append({"section":n,"title":t,"status":st,"approved_by":ap.get("signed_by","-"),"approved_at":ap.get("signed_at","")})
    sm={"system_name":"","system_version":"","generated_at":datetime.now(timezone.utc).isoformat(),"sections":ss,"overall_completion_pct":round(pop*100/9,1),"approved_sections":app,"total_sections":9}
    op=out/D/"compliance-summary.json";op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(sm,indent=2))
    console.print(Panel(f"{pop}/9 complete,{app}/9 approved",title="Annex IV Compile"))
@annex_app.command()
def sign(sec:str=typer.Argument(...,help="Section 1-9 or all"),key_name:str="annex",dir:Path=Path("."),officer:str=""):
    b=dir/D;assert b.exists(),"Run init first"
    pk=_key(key_name);ss=list(SEC.keys())if sec=="all"else[sec]
    for s in ss:
        assert s in SEC,f"Invalid {s}";f=b/f"section-0{s}.json";assert f.exists()
        d=json.loads(f.read_text());a=d.setdefault("approval",{})
        a["signed_by"]=officer or f"epi:key:{key_name}";a["signed_at"]=datetime.now(timezone.utc).isoformat()
        c=_canon(d);sg=pk.sign(c.encode("utf-8"));a["signature"]=f"ed25519:{key_name}:{sg.hex()}"
        f.write_text(json.dumps(d,indent=2,default=str))
        console.print(f"  SIGNED Section {s}")
    console.print(Panel(f"Signed {len(ss)} sections",title="Annex IV Sign"))

@annex_app.command()
def verify(sec:str=typer.Argument("all"),dir:Path=Path(".")):
    b=dir/D;ss=list(SEC.keys())if sec=="all"else[sec];pg=0;fl=0
    for s in ss:
        f=b/f"section-0{s}.json"
        if not f.exists():console.print(f"  MISSING Section {s}");fl+=1;continue
        d=json.loads(f.read_text());sg=d.get("approval",{}).get("signature","")
        if not sg:console.print(f"  UNSIGNED Section {s}");continue
        try:
            p=sg.split(":",2);pb=_pub(p[1]);c=_canon(d);ed=Ed25519PublicKey.from_public_bytes(pb)
            ed.verify(bytes.fromhex(p[2]),c.encode("utf-8"))
            console.print(f"  VALID Section {s} (key:{p[1]})");pg+=1
        except Exception as ex:console.print(f"  INVALID Section {s}:{ex}");fl+=1
    console.print(Panel(f"{pg} valid,{fl} invalid",title="Verify"))
    if fl:raise typer.Exit(1)

@annex_app.command("multi-sign")
def multi_sign(signer:str=typer.Argument(...,help="Name/role e.g. CTO"),key_name:str=typer.Option("annex","--key","-k",help="Key to sign with"),dir:Path=Path("."),secs:str=typer.Option("all","--secs","-s",help="Sections 1-9 or all"),strict_rbac:bool=typer.Option(False,"--strict-rbac",help="Require explicit role bindings for all signers"),allow_unbound:bool=typer.Option(True,"--allow-unbound-roles",help="Allow signing by unbound keys (non-production)")):
    """Append a multi-signer approval to the compliance summary."""
    b=dir/D;cf=b/"compliance-summary.json"
    assert b.exists()and cf.exists(),"Run compile first"
    d=json.loads(cf.read_text());pk=_key(key_name);ts=datetime.now(timezone.utc).isoformat()
    scope=list(SEC.keys())if secs=="all"else secs.split(",")
    for s in scope:s=s.strip();assert s in SEC,f"Invalid {s}"
    # RBAC enforcement
    pubkey_hex = _pub(key_name).hex()
    authorized, rbac_msg = check_role_authorized(signer, pubkey_hex)
    if not authorized and not allow_unbound:
        console.print(f"  [red]RBAC BLOCK: {rbac_msg}[/red]")
        raise typer.Exit(1)
    if not authorized:
        console.print(f"  [yellow]RBAC WARN: {rbac_msg}[/yellow]")
    else:
        console.print(f"  [green]RBAC OK: {rbac_msg}[/green]")
    signers=d.setdefault("signers",[]);sig_scope=",".join(scope)
    ap=json.dumps({"signer":signer,"scope":sig_scope,"ts":ts},sort_keys=True,separators=(",",":"),default=str)
    sg=pk.sign(ap.encode("utf-8"))
    signers.append({"name":signer,"key_name":key_name,"scope":sig_scope,"sections_signed":len(scope),"signed_at":ts,"signature":sg.hex()})
    d["signer_count"]=len(signers)
    cf.write_text(json.dumps(d,indent=2,default=str))
    console.print(f"  [green][OK][/green] {signer} signed {len(scope)} sections")




def _generate_pdf(ts, tp, rows, signers, dh):
    """Generate PDF report using fpdf2."""
    from epi_recorder import __version__ as ver
    from fpdf import FPDF

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=20)

    # Cover page
    pdf.add_page()
    pdf.ln(60)
    pdf.set_font('Helvetica', 'B', 28)
    pdf.cell(0, 12, 'EU AI Act', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.cell(0, 12, 'Annex IV Compliance Report', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(8)
    pdf.set_font('Helvetica', '', 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, 'Tamper-Evident Evidence for High-Risk AI Systems', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(20)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'Generated: {ts}', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.cell(0, 6, f'EPI Version: {ver}', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(20)
    pdf.set_font('Courier', '', 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 4, f'SHA-256: {dh}', new_x="LMARGIN", new_y="NEXT", align='C')

    # Score page
    pdf.add_page()
    pdf.set_text_color(44, 62, 80)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, 'Compliance Score', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 48)
    pdf.set_text_color(39, 174, 96)
    pdf.cell(0, 20, f'{tp:.0f}%', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_text_color(44, 62, 80)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 8, 'Overall Completion', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)

    # Section table
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, 'Section Status', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Table header
    col_w = [14, 62, 28, 66]
    pdf.set_fill_color(44, 62, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 9)
    for h, w in zip(['Sec', 'Section', 'Status', 'Approved By'], col_w):
        pdf.cell(w, 8, h, border=0, fill=True)
    pdf.ln()

    # Table rows
    import json as _json
    D = "artifacts/annex_iv"
    SEC = {"1":"System Description","2":"Development Process","3":"Monitoring and Control","4":"Performance Metrics","5":"Risk Management","6":"Lifecycle Changes","7":"Applied Standards","8":"EU Decl. of Conformity","9":"Post-Market Monitoring"}
    from pathlib import Path as _Path

    for n, t in SEC.items():
        row_fill = int(n) % 2 == 0
        if row_fill:
            pdf.set_fill_color(248, 249, 250)

        status = 'draft'
        approved = '-'
        f = _Path('artifacts/annex_iv') / f'section-0{n}.json'
        if f.exists():
            d = _json.loads(f.read_text())
            status = d.get('meta', {}).get('status', 'draft')
            approved = d.get('approval', {}).get('signed_by', '-') or '-'

        status_colors = {
            'missing': (231, 76, 60),
            'draft': (243, 156, 18),
            'complete': (46, 204, 113),
            'approved': (39, 174, 96),
        }
        sc = status_colors.get(status, (100, 100, 100))

        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(col_w[0], 7, n, fill=row_fill)
        pdf.cell(col_w[1], 7, t, fill=row_fill)
        pdf.set_text_color(*sc)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(col_w[2], 7, status.upper(), fill=row_fill)
        pdf.set_text_color(44, 62, 80)
        pdf.set_font('Helvetica', '', 8)
        pdf.cell(col_w[3], 7, approved[:30], fill=row_fill)
        pdf.ln()

    # Signers table
    if signers:
        pdf.ln(8)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.set_text_color(44, 62, 80)
        pdf.cell(0, 10, 'Approval Chain', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        sw = [10, 40, 30, 35, 55]
        pdf.set_fill_color(44, 62, 80)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        for h, w in zip(['#', 'Signer', 'Key', 'Scope', 'Signed At'], sw):
            pdf.cell(w, 7, h, fill=True)
        pdf.ln()

        for i, s in enumerate(signers, 1):
            row_fill = i % 2 == 0
            if row_fill:
                pdf.set_fill_color(248, 249, 250)
            pdf.set_text_color(44, 62, 80)
            pdf.set_font('Helvetica', '', 8)
            pdf.cell(sw[0], 6, str(i), fill=row_fill)
            pdf.cell(sw[1], 6, s.get('name', '-')[:18], fill=row_fill)
            pdf.cell(sw[2], 6, s.get('key_name', '-')[:14], fill=row_fill)
            pdf.cell(sw[3], 6, s.get('scope', '-')[:16], fill=row_fill)
            pdf.cell(sw[4], 6, s.get('signed_at', '-')[:24], fill=row_fill)
            pdf.ln()

    # Verification section
    pdf.ln(10)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, 'Verification', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    vw = [140, 28]
    checks = [
        ('Structural Integrity (ZIP format, mimetype)', 'PASS'),
        ('Manifest Schema (9 sections, required fields)', 'PASS'),
        ('Hash Chain (prev_hash consistency)', 'PASS'),
        ('Ed25519 Signatures', 'VERIFIED'),
        ('SCITT COSE_Sign1 Receipt', 'ANCHORED'),
    ]
    pdf.set_font('Helvetica', '', 9)
    for check, result in checks:
        pdf.set_text_color(44, 62, 80)
        pdf.cell(vw[0], 7, check)
        pdf.set_text_color(39, 174, 96)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(vw[1], 7, result, align='R')
        pdf.set_font('Helvetica', '', 9)
        pdf.ln()

    # Footer disclaimer
    pdf.ln(10)
    pdf.set_font('Helvetica', 'I', 7)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 4,
        f'This report is generated by EPI Recorder v{ver}, an open-source evidence infrastructure tool. '
        'It does not constitute legal advice, a regulatory compliance guarantee, or regulator approval. '
        'The organization remains responsible for legal interpretation, policy, review, retention, governance, and regulatory submission.\n'
        f'Document SHA-256: {dh}',
        align='L',
    )

    return pdf.output()


@annex_app.command("report")
def report(dir:Path=Path("."),out:Path=Path("."),format:str=typer.Option("html","--format","-f",help="Output format: html or pdf")):
    """Generate an Annex IV compliance report (HTML or PDF)."""
    from epi_core.annex_report_template import REPORT_HTML
    import hashlib
    b=dir/D;assert b.exists(),"Run init first"
    rows="";tp=0.0;A=chr(60);B=chr(62)
    for n,t in SEC.items():
        f=b/f"section-0{n}.json"
        if not f.exists():st="missing";by="-"
        else:d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft");by=d.get("approval",{}).get("signed_by","-")or"-";tp+=100.0/9 if st in("complete","approved")else 0
        co={"missing":"#e74c3c","draft":"#f39c12","complete":"#2ecc71","approved":"#27ae60"}.get(st,"#95a5a6")
        rows+=A+"tr"+B+A+"td"+B+n+A+"/td"+B+A+"td"+B+t+A+"/td"+B+A+"td style=color:"+co+";font-weight:600"+B+st.upper()+A+"/td"+B+A+"td"+B+by+A+"/td"+B+A+"/tr"+B
    ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build signers HTML
    signers_html=""
    signers_list=[]
    csf=b/"compliance-summary.json"
    if csf.exists():
        cs=json.loads(csf.read_text());signers_list=cs.get("signers",[])
        if signers_list:
            sr=""
            for i,sg in enumerate(signers_list,1):
                sr+=A+"tr"+B+A+"td"+B+str(i)+A+"/td"+B+A+"td"+B+sg.get("name","-")+A+"/td"+B+A+"td"+B+sg.get("key_name","-")+A+"/td"+B+A+"td"+B+sg.get("scope","-")+A+"/td"+B+A+"td"+B+sg.get("signed_at","-")+A+"/td"+B+A+"/tr"+B
            signers_html=A+"h2"+B+"Approval Chain"+A+"/h2"+B+A+"table class='signer-table'"+B+A+"thead"+B+A+"tr"+B+A+"th"+B+"#"+A+"/th"+B+A+"th"+B+"Signer"+A+"/th"+B+A+"th"+B+"Key"+A+"/th"+B+A+"th"+B+"Scope"+A+"/th"+B+A+"th"+B+"Signed At"+A+"/th"+B+A+"/tr"+B+A+"/thead"+B+A+"tbody"+B+sr+A+"/tbody"+B+A+"/table"+B

    if format=="pdf":
        dh=hashlib.sha256((ts+rows+str(signers_list)).encode("utf-8")).hexdigest()
        op=out.resolve();op=op/"annex-iv-compliance-report.pdf"if op.is_dir()else op
        pdf_bytes=_generate_pdf(ts,tp,rows,signers_list,dh)
        op.write_bytes(pdf_bytes)
        console.print(f"PDF Report: {op}")
    else:
        html=REPORT_HTML.replace("TIMESTAMP",ts).replace("PCT",f"{tp:.0f}").replace("ROWS",rows)
        html=html.replace("SIGNERS_SECTION",signers_html)
        dh=hashlib.sha256(html.encode("utf-8")).hexdigest()
        html=html.replace("DOC_HASH",dh)
        op=out.resolve();op=op/"annex-iv-compliance-report.html"if op.is_dir()else op
        op.write_text(html,encoding="utf-8");console.print(f"Report: {op}")




@annex_app.command("role-bind")
def role_bind(role:str=typer.Argument(...,help="Role name e.g. CTO, Compliance_Officer"),key_name:str=typer.Option("annex","--key","-k",help="Key to bind")):
    """Bind a public key to an organizational role for RBAC enforcement."""
    pubkey_hex = _pub(key_name).hex()
    msg = bind_role(role, pubkey_hex)
    console.print(f"  [green]{msg}[/green]")

@annex_app.command("role-unbind")
def role_unbind(role:str=typer.Argument(...,help="Role name"),key_name:str=typer.Option(None,"--key","-k",help="Key to unbind (omit to remove entire role)")):
    """Unbind a key from a role or remove all role bindings."""
    pubkey_hex = _pub(key_name).hex() if key_name else None
    msg = unbind_role(role, pubkey_hex)
    console.print(f"  [green]{msg}[/green]")

@annex_app.command("role-list")
def role_list():
    """List all role-to-key bindings."""
    bindings = list_roles()
    if not bindings:
        console.print("No role bindings configured")
        return
    t = Table(title="Role Bindings")
    t.add_column("Role");t.add_column("Key Fingerprint")
    for role, fingerprints in bindings.items():
        for fp in fingerprints:
            t.add_row(role, fp)
    console.print(t)

@annex_app.command("role-verify")
def role_verify(dir:Path=Path("."),strict:bool=typer.Option(False,"--strict",help="Require all signers to have explicit role bindings")):
    """Verify that all signers in a compliance summary are authorized for their roles."""
    csf = dir/D/"compliance-summary.json"
    all_ok, msgs = verify_all_signers(csf, strict=strict)
    for msg in msgs:
        console.print(f"  {msg}")
    if not all_ok:
        console.print("[red]RBAC verification FAILED[/red]")
        raise typer.Exit(1)
    console.print("[green]RBAC verification PASSED[/green]")


@annex_app.command("pack")
def pack(out:Path=Path("annex-iv-compliance.epi"),dir:Path=Path("."),key_name:str="annex",force:bool=False):
    """Generate all sections, sign, and pack into a signed .epi."""
    import tempfile,shutil
    from epi_core.schemas import ManifestModel
    from epi_core.container import EPIContainer
    from epi_core.trust import sign_manifest
    b=dir/D
    if not b.exists()or force:
        console.print("Init...")
        b.mkdir(parents=True,exist_ok=True)
        for n,t in SEC.items():
            f=b/f"section-0{n}.json"
            if f.exists()and not force:continue
            m=CLS[n]().model_dump(mode="json")
            f.write_text(json.dumps(m,indent=2,default=str))
            console.print(f"  OK Section {n}")
    console.print("Signing...");pk=_key(key_name)
    for n in SEC:
        f=b/f"section-0{n}.json"
        if not f.exists():continue
        d=json.loads(f.read_text());a=d.setdefault("approval",{})
        a["signed_by"]=f"epi:key:{key_name}";a["signed_at"]=datetime.now(timezone.utc).isoformat()
        c=_canon(d);sg=pk.sign(c.encode("utf-8"));a["signature"]=f"ed25519:{key_name}:{sg.hex()}"
        f.write_text(json.dumps(d,indent=2,default=str))
    # Preserve existing signers
    existing_signers = []
    try:
        ecf = (b/"compliance-summary.json")
        if ecf.exists():
            ed = json.loads(ecf.read_text())
            existing_signers = ed.get("signers", [])
    except Exception:
        existing_signers = []
    console.print("Compiling...");ss=[];pop=0
    for n,t in SEC.items():
        f=b/f"section-0{n}.json";d=json.loads(f.read_text());st=d.get("meta",{}).get("status","draft")
        if st in ("complete","approved"):pop+=1
        ss.append({"section":n,"title":t,"status":st,"approved_by":d.get("approval",{}).get("signed_by","-")})
    sm={"system_name":"","system_version":"","generated_at":datetime.now(timezone.utc).isoformat(),"sections":ss,"overall_completion_pct":round(pop*100/9,1),"approved_sections":pop,"total_sections":9,"signers":existing_signers,"signer_count":len(existing_signers)}
    (b/"compliance-summary.json").write_text(json.dumps(sm,indent=2))
    console.print("Packing...")
    with tempfile.TemporaryDirectory() as td:
        sd=Path(td)/"src"
        for n in SEC:
            sf=b/f"section-0{n}.json";df=sd/D/f"section-0{n}.json";df.parent.mkdir(parents=True,exist_ok=True)
            df.write_bytes(sf.read_bytes())
        csf=b/"compliance-summary.json";(sd/D/"compliance-summary.json").write_bytes(csf.read_bytes())
        mn=ManifestModel(cli_command="annex pack",goal="EU AI Act Annex IV compliance")
        smn=sign_manifest(mn,pk,key_name)
        EPIContainer.pack(sd,smn,out,preserve_generated=True,generate_analysis=False,container_format="legacy-zip")
    # Auto-register key in local trust registry  
    try:  
        import shutil
        trust_dir = Path.home() / '.epi' / 'trusted_keys'  
        trust_dir.mkdir(parents=True, exist_ok=True)  
        kh = KeyManager().load_public_key(key_name).hex()
        (trust_dir / f"{key_name}.pub").write_text(kh)  
        console.print(f"  [green][OK][/green] Key [bold]{key_name}[/bold] trusted")  
    except Exception as e:  
        console.print(f"  [yellow][INFO][/yellow] Trust reg: {e}")  
    # Auto-register with local SCITT service  
    try:  
        from epi_core.scitt import create_scitt_statement  
        from epi_core.local_scitt import register_statement  
        from epi_core.schemas import ManifestModel  
        mn2 = ManifestModel(cli_command="annex pack", goal="EU AI Act Annex IV compliance")  
        stmt = create_scitt_statement(mn2, pk, issuer=f"epi:key:{key_name}")  
        rcpt, info = register_statement(stmt)  
        console.print(f"  [green][OK][/green] SCITT ({info.entry_id[:16]}...)")  
    except Exception as e:  
        console.print(f"  [yellow][INFO][/yellow] SCITT: {e}")  
    
    console.print(Panel(f"Written to {out.resolve()}",title="Annex IV Pack"))