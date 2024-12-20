"""
main file - every important pieces of code should be in there
"""

# pylint: disable=import-error

import os
import sys
import warnings
import logging
from multiprocessing import Pool
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from skimage import filters
from mayavi import mlab
import scipy.ndimage
from skimage import data, morphology
from skimage.util import img_as_ubyte
from skimage import exposure
from src.utils.testutils import generate_timestamp, check_os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

timestamp = generate_timestamp()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("logfile.log")
formatter = logging.Formatter(f"{timestamp}: %(levelname)s : %(name)s : %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

warnings.filterwarnings("ignore", message=".*iCCP: known incorrect sRGB profile.*")

os_type = check_os()

if os_type == "Windows":
    BASE_PATH = "..\\pictures"
elif os_type == "Linux":
    BASE_PATH = "./pictures"
elif os_type == "MacOS":
    BASE_PATH = "./pictures"
else:
    print("Unknown OS! Using default path.")
    BASE_PATH = "./pictures"


def interpolate_image_stack(image_stack, scaling_factor, order=1):
    """
    Interpolates a 3D image stack using the specified scaling factor and interpolation order.

    Args:
        image_stack (numpy.ndarray): The input 3D image stack.
        scaling_factor (float): The scaling factor for resizing the images.
        order (int): The interpolation order (default: 1 for bilinear interpolation).

    Returns:
        numpy.ndarray: The interpolated 3D image stack.
    """
    interpolated_stack = scipy.ndimage.zoom(
        image_stack,
        (scaling_factor, scaling_factor, scaling_factor),
        order=order
    )
    return interpolated_stack


def save_to_tiff_stack(image_array, filepath):
    """
    Saves an array of processed images as a multi-page TIFF file.

    This function converts a NumPy array of images into TIFF format and saves it to the specified file path.

    Args:
        image_array (numpy.ndarray): Array of processed images to save.
        filepath (str): Path where the TIFF file will be saved.

    Returns:
        None: The function saves the file directly and does not return a value.

    Raises:
        ValueError: If the image_array is empty.
        IOError: If an error occurs while saving the file.
    """
    from PIL import Image
    import numpy as np

    if image_array.size == 0:
        raise ValueError("The image_array must not be empty.")

    images = [Image.fromarray((image * 255).astype(np.uint8)) for image in image_array]
    images[0].save(filepath, save_all=True, append_images=images[1:])
    print(f"Saved data to TIFF stack: {filepath}")


# loads image
def load_image(filepath):
    """
    Loads an image from the specified file and converts it to a grayscale image.

    Args:
        filepath (str): The path to the image file to be loaded.

    Returns:
        numpy.ndarray: A 2D array representing the grayscale image.
    """
    im = Image.open(filepath).convert("L")
    return np.array(im)


def process_image(image):
    """
    Processes the input image by applying Gaussian blur and converting it to a binary image.

    Args:
        image (numpy.ndarray): A 2D array representing the input grayscale image.

    Returns:
        tuple: A tuple containing:
            - numpy.ndarray: The blurred image after applying Gaussian filter.
            - numpy.ndarray: A binary image where pixels are set to True
            if they are above the Otsu threshold,
            and False otherwise.
    """
    image_blurred = filters.gaussian(image, sigma=1, mode="constant")

    average_intensity = np.mean(image_blurred)

    binary_image = image_blurred > filters.threshold_otsu(image_blurred)
    return image_blurred, binary_image, average_intensity


from skimage import measure

def process_and_visualize(directory):
    """
    Processes and visualizes all important images in the specified directory.

    This function loads all TIFF images from the given directory,
    applies image processing techniques,
    and visualizes the results, including blurred images, binary images, and histograms.

    Args:
        directory (str): The path to the directory containing the image files.

    Returns:
        None: This function does not return any value. It performs visualization and printing of results.
    """
    # Lade die Bilder aus dem Verzeichnis
    filepaths = [
        os.path.join(directory, filename)
        for filename in sorted(os.listdir(directory))
        if filename.endswith(".tif")
    ]

    with Pool() as pool:
        data_array = pool.map(load_image, filepaths)

    data_array = np.array(data_array)
    print("Data array shape:", data_array.shape)

    # Verarbeite die Bilder
    with Pool() as pool:
        results = pool.map(process_image, data_array)

    image_blurred_array, binary_image_array, average_intensities = zip(*results)
    binary_image_array = np.array(binary_image_array)

    # Morphologische Schließung anwenden
    closed_binary_images = np.array([
        morphology.closing(image, footprint=morphology.disk(6))
        for image in binary_image_array
    ])

    # Interpolation auf die geschlossenen Bilder anwenden
    binary_image_array_interpolated = interpolate_image_stack(closed_binary_images, 0.5)

    # Größten Cluster finden
    labels, num_clusters = measure.label(binary_image_array_interpolated, background=0, return_num=True, connectivity=1)
    cluster_sizes = np.bincount(labels.flatten())
    largest_cluster_label = cluster_sizes[1:].argmax() + 1  # +1, da Label 0 der Hintergrund ist
    largest_cluster = (labels == largest_cluster_label)

    print(f"Anzahl der Cluster: {num_clusters}")
    print(f"Größe des größten Clusters: {cluster_sizes[largest_cluster_label]}")

    # Speichern des größten Clusters als neuer Stack
    save_to_tiff_stack(largest_cluster.astype(np.uint8),
                       f"./data/stream/{timestamp}_largest_cluster.tif")

    # 3D-Visualisierung des größten Clusters
    # visualize_3d(largest_cluster)

    # Durchschnittliche Intensität berechnen
    overall_average_intensity = np.mean(average_intensities) * 255
    print(f"Average Intensity of the whole stack: {overall_average_intensity}")

    # Verarbeiteten Stack speichern
    save_to_tiff_stack(binary_image_array_interpolated,
                       f"./data/stream/{timestamp}_binary_output_stack.tif")




# shows images and saves them in a specific directory
def plot_images(image_array, title):
    """
    Plots a grid of images from the provided array and saves the plot as a PNG file.

    This function takes a 3D array of images, arranges them in a grid format, and displays them
    using Matplotlib. The plot is saved to a specified directory with a timestamp in the filename.
t
    Args:
        image_array (numpy.ndarray):
        A 3D array where each slice along the first dimension represents an image.
        title (str): The title to be displayed above each image in the plot.

    Returns:
        None: This function does not return any value. It performs visualization
        and saves the plot as a file.
    """
    num_images = image_array.shape[0]
    cols = 3
    rows = (num_images // cols) + (num_images % cols > 0)

    plt.figure(figsize=(15, 5 * rows))
    for i in range(num_images):
        plt.subplot(rows, cols, i + 1)
        plt.imshow(image_array[i], cmap="gray")
        plt.title(f"{title} {i + 1}")
        plt.axis("off")
    plt.tight_layout()
    file_path = f"{BASE_PATH}/plot_{timestamp}.png"
    plt.savefig(file_path)
    plt.show()
    print("Plot images were loaded")


# shows histogram
def plot_histogram(image_array):
    """
    Plots a histogram of pixel values from the provided image array.

    This function takes a 3D array of images, flattens it to extract all pixel values, and creates
    a histogram to visualize the distribution of pixel intensities across the images. The histogram
    is saved as a PNG file.

    Args:
        image_array (numpy.ndarray):
        A 3D array where each slice along the first dimension represents an image.

    Returns:
        None: This function does not return any value. It performs visualization
        and saves the histogram as a file.
    """
    plt.figure(figsize=(10, 6))
    all_pixel_values = image_array.flatten()
    plt.hist(all_pixel_values, bins=256, range=(0, 1), color="gray", alpha=0.7)
    plt.title("Histogram of Pixel Values of Processed Images")
    plt.xlabel("Pixel Values")
    plt.ylabel("Frequency")
    plt.xlim(0, 1)
    plt.grid()
    file_path = f"{BASE_PATH}/histogram_{timestamp}.png"
    plt.savefig(file_path)
    print("Plot histogram was created")


def visualize_3d(image_array):
    """
    Creates and displays a 3D visualization of the provided image array.

    This function takes a 3D array of images and generates a 3D contour plot using Mayavi.
    The plot is saved as a PNG file.

    Args:
        image_array (numpy.ndarray):
        3D array where each slice along the first dimension represents an image.

    Returns:
        None: This function does not return any value. It performs visualization
        and saves the 3D plot as a file.
    """
    mlab.figure(size=(800, 800), bgcolor=(1, 1, 1))
    mlab.contour3d(image_array, contours=8, opacity=0.5, colormap="bone")
    file_path = f"{BASE_PATH}/3d_visualize_{timestamp}.png"
    mlab.savefig(file_path)
    mlab.show()


if __name__ == "__main__":
    logger.debug("Running")
    print("Running simulation")

    if check_os() == "Windows":
        DIRECTORY = "..\\data\\dataset"
    elif check_os() == "Linux":
        DIRECTORY = "/home/mathias/PycharmProjects/BoneSimulation/data/dataset"
    elif check_os() == "MacOS":
        DIRECTORY = "./data/dataset"
        # not familiar with macOS, please check
    else:
        print("Unknown OS!")
        DIRECTORY = None

    if DIRECTORY is not None:
        print(f"Directory found: {DIRECTORY}")
        process_and_visualize(DIRECTORY)
    else:
        print("No valid directory found. Exiting.")