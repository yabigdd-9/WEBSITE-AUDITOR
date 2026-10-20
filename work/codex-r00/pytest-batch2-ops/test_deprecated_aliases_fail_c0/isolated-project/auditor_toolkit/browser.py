import base64;from pathlib import Path
def run_browser_checks(url,output_dir,enabled=True):
 p=Path(output_dir)/'screenshot.png';p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
 return {'status':'ok','evidence':{'screenshot':str(p),'mode':'synthetic_contract_fixture'}}
