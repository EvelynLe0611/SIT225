# make_annotation.py
# SIT225 6D - Build the annotation file for the captured data.
#
# For each captured pair (N_yyyymmddHHMMss.csv / .jpg) it shows you the image,
# prints simple stats from the matching data, and asks for a label:
#     0 = no-activity, 1 = activity 1, 2 = activity 2
# The result is written to annotations.csv with two columns: filename, label
#
# Run:  python make_annotation.py
#   - press 0, 1, or 2 then Enter to label
#   - the data stats help when the image alone is ambiguous (Q3)

import os
import csv
import glob
import statistics

import cv2

OUT_DIR = "captures"
ANNOTATION_FILE = "annotations.csv"


def data_stats(csv_path):
    """Return a short summary of movement in each axis to help decide the activity."""
    xs, ys, zs = [], [], []
    with open(csv_path) as f:
        r = csv.DictReader(f)
        for row in r:
            xs.append(float(row["x"]))
            ys.append(float(row["y"]))
            zs.append(float(row["z"]))

    def spread(vals):
        # standard deviation is a simple measure of how much an axis moved
        return statistics.pstdev(vals) if len(vals) > 1 else 0.0

    return {
        "n": len(xs),
        "std_x": round(spread(xs), 3),
        "std_y": round(spread(ys), 3),
        "std_z": round(spread(zs), 3),
    }


def main():
    csv_files = sorted(glob.glob(os.path.join(OUT_DIR, "*.csv")))
    if not csv_files:
        print("No CSV files found in", OUT_DIR)
        return

    rows = []
    for csv_path in csv_files:
        base = os.path.splitext(os.path.basename(csv_path))[0]
        jpg_path = os.path.join(OUT_DIR, base + ".jpg")

        s = data_stats(csv_path)
        print("\n" + "=" * 50)
        print(f"File: {base}")
        print(f"  samples: {s['n']}  |  movement (std)  "
              f"x={s['std_x']}  y={s['std_y']}  z={s['std_z']}")

        # show the image so you can decide the activity
        if os.path.exists(jpg_path):
            img = cv2.imread(jpg_path)
            if img is not None:
                cv2.imshow("activity image (press any key)", img)
                cv2.waitKey(1)
        else:
            print("  (no image found)")

        label = ""
        while label not in ("0", "1", "2"):
            label = input("  label 0 = no-activity 1 = activity1 2 = activity2 > ").strip()

        # store the image filename (task pairs the label with the activity image)
        rows.append([base + ".jpg", label])
        cv2.destroyAllWindows()

    with open(ANNOTATION_FILE, "w", newline = "") as f:
        w = csv.writer(f)
        w.writerow(["filename", "label"])
        w.writerows(rows)

    print("\nWrote", ANNOTATION_FILE, "with", len(rows), "rows")


if __name__ == "__main__":
    main()