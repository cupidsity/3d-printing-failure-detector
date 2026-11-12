import asyncio
import sys

import cv2
import numpy as np
import matplotlib.pyplot as plt

# edge_detect: This module should receive a pre-processed image from main. With this image, the module 
# processes the image further into an edge bitmap. This output is then evaluate using several subfunctions
# and graded. This grade is returned as a float ranging from 0 to 1 inclusive, which represents how confident
# we are that the print has failed

# Baseline tuning for canny
BLUR_KERNEL = (5,5)


# Select test print image, debug function, takes 
def select_image_file(title: str) -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title=title,
        filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
    )
    root.destroy()
    return path

# Debug function for testing canny with a live image feed
def live_capture():
    cap = cv2.VideoCapture(1)

    while True:
        #Capture frame-by-frame
        ret, frame = cap.read()
        if not ret:
            break

        #Convert frame to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        #Apply Gaussian Blur to reduce background image noise
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        
        #Apply Canny Edge Detection (minVal=50, maxVal=150)
        edges = cv2.Canny(blur, 50, 150)

        #Display the resulting live edge map
        cv2.imshow('Live Canny Edge Detection', edges)

        #Press 'q to exit loop
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Clear everything once the stream is finished
    cap.release()
    cv2.destroyAllWindows()

# First part of the process. This function takes in the filepath to the image, then applies the canny algorithm. This should return
# a binary edge map, where 0 is no edge, and 1 indicates an edge. We also have global tuning variables to easily adjust.

def process_image(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    assert img is not None, "file could not be read"

    blur = cv2.GaussianBlur(img, BLUR_KERNEL, 0)
    edge = cv2.Canny(img, 100, 200)

    return blur, edge

# This function calculates the orientation entropy of our edge map using a Shannon Entropy. This essentially calculates the order (or disorder)
# within our edge map. It should take in the blur kernel, and the pre-processed edge map. After evaluating, it should return a float from 0 to 1
# corresponding to how likely it is to indicate a failed print.

def orientation_entropy(blur: np.ndarray, edges: np.ndarray, num_bins=24) -> float:
    from scipy.stats import entropy
    gx = cv2.Sobel(blur, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(blur, cv2.CV_32F, 0, 1)

    magnitude, angle = cv2.cartToPolar(gx, gy)

    mask = edges > 0
    if not mask.any():
        return 0.0

    angles = np.mod(angle[mask], np.pi)
    hist, _ = np.histogram(angles, bins=num_bins, range=(0, np.pi), weights=magnitude[mask])

    total = hist.sum()
    if total <= 0:
        return 0.0

    return float(entropy(hist / total, base=num_bins))

def connected_components(edges: np.ndarray) -> float:
    print()

def edge_density(edges: np.ndarray, roi_area: int) -> float:
    return cv2.countNonZero(edges) / max(roi_area, 1)

# The overall statistics of the connected components within the edges map. Takes in the edge map and returns three stats.
# The number of components, how many of them are lower than 30 pixels (Tunable), and how much of the print space the largest component takes
def component_stats(edges: np.ndarray) -> dict:
    n, _, stats, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    sizes = stats[1:, cv2.CC_STAT_AREA]

    return {
        "count": int(len(sizes)),
        "tiny_frac": float(np.mean(sizes < 30)),
        "largest_share": float(sizes.max() / sizes.sum())
    }

def print_all_stats(edges, blur):
    stats = component_stats(edges)
    print("Statistics:")
    print(f"Entropy: {orientation_entropy(blur, edges)}")
    print(f"Pixel Density: {edge_density(edges, edges.size)}")
    print(f"Tiny fraction: {stats["tiny_frac"]}")
    print(f"Largest Share: {stats["largest_share"]}")
    print(f"Component Count: {stats["count"]}")

# Main evaluation algorithm. Should apply three grading processes
def analyze_image(path):
    print()

def main():
    file = select_image_file("Choose an image")
    blur, edge_map = process_image(file)
    plt.imshow(edge_map, cmap = 'gray')
    plt.show()
    print(f"Statistics: ")
    print_all_stats(edge_map, blur)

main()