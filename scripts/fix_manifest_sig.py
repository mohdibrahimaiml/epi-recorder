import sys,os,json,hashlib,zipfile,subprocess
src_epi=sys.argv[1] if len(sys.argv)>1 else os.path.join(os.environ["USERPROFILE"],"epi-recorder","annex-iv-compliance.epi")
key_name=sys.argv[2] if len(sys.argv)>2 else "annex"
tmp_epi=os.path.join(os.environ["USERPROFILE"],"annex-fixed.epi")
from epi_core.keys import KeyManager
from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
zf=zipfile.ZipFile(src_epi,"r")
md=json.loads(zf.read("manifest.json"))
zf.close()
m=ManifestModel(**md)
h=get_canonical_hash(m,exclude_fields={"signature"})
pk=KeyManager().load_private_key(key_name)
sig=pk.sign(bytes.fromhex(h))
pk_hex=m.public_key
kname=hashlib.sha256(pk_hex.encode("utf-8")).hexdigest()[:16]
md["signature"]="ed25519:%s:%s"%(kname,sig.hex())
pk_bytes=bytes.fromhex(pk_hex)
Ed25519PublicKey.from_public_bytes(pk_bytes).verify(bytes.fromhex(sig.hex()),bytes.fromhex(h))
zf_in=zipfile.ZipFile(src_epi,"r")
zf_out=zipfile.ZipFile(tmp_epi,"w",zipfile.ZIP_DEFLATED)
for item in zf_in.infolist():
   if item.filename=="manifest.json":
       zf_out.writestr(item,json.dumps(md,indent=2))
   else:
       zf_out.writestr(item,zf_in.read(item.filename))
zf_in.close()
zf_out.close()
print("FIXED_SIG")
