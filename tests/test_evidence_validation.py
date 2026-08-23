
from pathlib import Path
import numpy as np, rasterio
from rasterio.transform import from_origin
from earth_one.evidence_validation import compare_rasters, promote_evidence
from earth_one.reproducibility import verify_change_reconstruction

def _w(path, arr):
    profile={"driver":"GTiff","height":arr.shape[0],"width":arr.shape[1],"count":1,"dtype":"float32",
             "crs":"EPSG:4326","transform":from_origin(0,2,1,1),"nodata":np.nan}
    with rasterio.open(path,"w",**profile) as ds: ds.write(arr.astype("float32"),1)

def test_reproducibility_exact(tmp_path):
    a=tmp_path/"a.tif"; b=tmp_path/"b.tif"; d=tmp_path/"d.tif"
    _w(a,np.array([[0.2,0.3],[0.4,0.5]])); _w(b,np.array([[0.3,0.4],[0.5,0.6]]))
    _w(d,np.array([[0.1,0.1],[0.1,0.1]]))
    r=verify_change_reconstruction(a,b,d)
    assert r["pass"]

def test_compare_reference(tmp_path):
    a=tmp_path/"a.tif"; b=tmp_path/"b.tif"
    _w(a,np.array([[0.2,-0.1],[0.3,-0.2]])); _w(b,np.array([[1,-2],[1,-2]]))
    r=compare_rasters(a,a)
    assert r["valid"]
    assert r["rmse"]==0

def test_evidence_promotion():
    r=promote_evidence(real_data_pass=True,reproducibility_pass=True,
                        independent_reference_pass=False,end_to_end_pass=False)
    assert r["status"]=="REAL_DATA_VALIDATED"
    assert not r["paper_claim_allowed"]
