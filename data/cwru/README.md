# CWRU Bearing Data Center — Download Instructions

## About
The **Case Western Reserve University (CWRU) Bearing Data Center** provides vibration signals
recorded from a motor-driven test rig with seeded bearing faults. This is the most widely used
benchmark dataset in bearing fault diagnosis research.

**Website:** https://engineering.case.edu/bearingdatacenter

## Files Required (12k Drive End, 0.007" fault diameter)

Download the following `.mat` files and place them in this `data/cwru/` folder:

### Normal Baseline
| File | Load (HP) | Link |
|------|-----------|------|
| `97.mat` | 0 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/97 |
| `98.mat` | 1 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/98 |
| `99.mat` | 2 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/99 |
| `100.mat` | 3 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/100 |

### Inner Race Fault (0.007")
| File | Load (HP) | Link |
|------|-----------|------|
| `105.mat` | 0 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/105 |
| `106.mat` | 1 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/106 |
| `107.mat` | 2 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/107 |
| `108.mat` | 3 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/108 |

### Ball Fault (0.007")
| File | Load (HP) | Link |
|------|-----------|------|
| `118.mat` | 0 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/118 |
| `119.mat` | 1 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/119 |
| `120.mat` | 2 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/120 |
| `121.mat` | 3 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/121 |

### Outer Race Fault @ 6 o'clock (0.007")
| File | Load (HP) | Link |
|------|-----------|------|
| `130.mat` | 0 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/130 |
| `131.mat` | 1 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/131 |
| `132.mat` | 2 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/132 |
| `133.mat` | 3 HP | https://engineering.case.edu/bearingdatacenter/download-data-file/133 |

## Quick Download (PowerShell)

```powershell
$files = @(97,98,99,100,105,106,107,108,118,119,120,121,130,131,132,133)
foreach ($f in $files) {
    Write-Host "Downloading $f.mat..."
    Invoke-WebRequest -Uri "https://engineering.case.edu/bearingdatacenter/download-data-file/$f" -OutFile "$f.mat"
}
```

## Notes
- Normal baseline files (97–100) are sampled at **48 kHz**; fault files at **12 kHz**.
  The training script automatically resamples normal signals to 12 kHz.
- All signals are from the **Drive End (DE) accelerometer**.
- Fault diameter: 0.007 inches (smallest available).
