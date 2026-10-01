# Part 2: Instance Creation Timing

Three VM instances were created from a custom image of the Part 1 Flask VM, and the creation time of each was measured.

## Setup

| Item | Value |
|---|---|
| Source VM | `flask-vm` (Part 1, Flask app installed) |
| Snapshot | `base-snapshot-flask-vm` |
| Image | `base-image-flask-vm` (created from the snapshot) |
| Zone | `us-west1-b` |
| Clone machine type | `e2-medium` |

## Results

| Instance | Creation time (seconds) |
|---|---|
| `flask-vm-clone-1` | 9.84 |
| `flask-vm-clone-2` | 10.79 |
| `flask-vm-clone-3` | 9.72 |
| **Average** | **10.12** |

## Notes

- **How time is measured:** from just before the `instances.insert` API call until the zone operation reports `DONE`. This covers VM creation, not the time for the OS to finish booting or for Flask to start.
- **Machine type:** `e2-micro` and `e2-small` were out of stock in `us-west1-b` (`ZONE_RESOURCE_POOL_EXHAUSTED`) when this ran, so the clones use `e2-medium`.
- **Takeaway:** starting from a saved image, each new, fully configured VM was ready in about 10 seconds, compared with several minutes to install Flask from scratch with a startup script in Part 1.
