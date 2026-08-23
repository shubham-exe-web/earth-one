
from pathlib import Path
import numpy as np, rasterio
from rasterio.transform import from_origin
from earth_one.temporal_experiment import TemporalExperimentConfig, run_temporal_experiment

def _write(path, arr):
    profile={"driver":"GTiff","height":arr.shape[0],"width":arr.shape[1],"count":1,
             "dtype":"float32","crs":"EPSG:4326","transform":from_origin(0,1,1,1),"nodata":np.nan}
    with rasterio.open(path,"w",**profile) as ds: ds.write(arr.astype("float32"),1)

def test_temporal_experiment_optical_only(tmp_path):
    a=tmp_path/"a.tif"; b=tmp_path/"b.tif"
    _write(a,np.array([[0.2,0.3],[0.4,0.5]]))
    _write(b,np.array([[0.3,0.4],[0.5,0.6]]))
    cfg=TemporalExperimentConfig("x",[0,0,1,1],"2025","2026",str(a),str(b))
    r=run_temporal_experiment(cfg,tmp_path/"out")
    assert abs(r["optical"]["NDVI"]["mean_delta"] - 0.1) < 1e-6
    assert r["multimodal"]["status"] == "not_available"

def test_temporal_experiment_full_modalities(tmp_path):
    files={}
    grids = {
        "nd25": np.array([[0.2,0.21],[0.22,0.23]]),
        "nd26": np.array([[0.3,0.31],[0.32,0.33]]),
        "vv25": np.array([[0.1,0.11],[0.12,0.13]]),
        "vv26": np.array([[0.2,0.21],[0.22,0.23]]),
        "vh25": np.array([[0.05,0.06],[0.07,0.08]]),
        "vh26": np.array([[0.15,0.16],[0.17,0.18]]),
    }
    for name,arr in grids.items():
        p=tmp_path/f"{name}.tif"; _write(p,arr); files[name]=p
    cfg=TemporalExperimentConfig("x",[0,0,1,1],"2025","2026",
        str(files["nd25"]),str(files["nd26"]),str(files["vv25"]),str(files["vv26"]),
        str(files["vh25"]),str(files["vh26"]))
    r=run_temporal_experiment(cfg,tmp_path/"out")
    assert r["multimodal"]["all_three_same_direction"] is True
