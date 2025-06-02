#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#

# Store the initial physical working directory
INITIAL_PWD=$(pwd -P)

# --- Configuration ---
INPUT_IMAGE_TYPE="JPG" # Default image type if -t is not specified
OUTPUT_FRAMERATE="24"
OUTPUT_FILENAME="kaust_vignette.mp4"
VIDEO_QUALITY_CRF="22" # Constant Rate Factor (0=lossless, 51=worst, 18-28 good range)
ENCODER_PRESET="slow" # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
TARGET_DIR_PREFIX="movie_frames_temp" # Prefix for temporary directory

# --- Helper Functions ---
function display_help() {
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo "This script creates a video slideshow from a directory of images of a specified type."
    echo
    echo "Options:"
    echo "  -h              Display this help message."
    echo "  -d <directory>  Specify a directory containing the images (default: current directory)."
    echo "  -o <filename>   Specify the output video filename (default: ${OUTPUT_FILENAME})."
    echo "  -f <fps>        Set the video framerate (default: ${OUTPUT_FRAMERATE})."
    echo "  -q <crf>        Set the CRF quality (0-51, default: ${VIDEO_QUALITY_CRF})."
    echo "  -p <preset>     Set the encoder preset (default: ${ENCODER_PRESET})."
    echo "  -t <type>       Specify input image type (e.g., JPG, PNG, TIF, TIFF, JPEG. Default: ${INPUT_IMAGE_TYPE})."
    echo
    echo "Example: $(basename "$0") -d ./my_png_images -t PNG -o my_png_video.mp4"
    echo "         $(basename "$0") -d ./my_tiff_images -t TIF"
}

# --- Argument Parsing ---
IMAGE_SOURCE_DIR="." # Default to current directory

while getopts ":hd:o:f:q:p:t:" opt; do
  case ${opt} in
    h )
      display_help
      exit 0
      ;;
    d )
      IMAGE_SOURCE_DIR="$OPTARG"
      ;;
    o )
      OUTPUT_FILENAME="$OPTARG"
      ;;
    f )
      OUTPUT_FRAMERATE="$OPTARG"
      ;;
    q )
      VIDEO_QUALITY_CRF="$OPTARG"
      ;;
    p )
      ENCODER_PRESET="$OPTARG"
      ;;
    t )
      INPUT_IMAGE_TYPE="${OPTARG}"
      ;;
    \? )
      echo "Invalid option: -$OPTARG" 1>&2
      display_help
      exit 1
      ;;
    : )
      echo "Invalid option: -$OPTARG requires an argument" 1>&2
      display_help
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

if [ ! -d "$IMAGE_SOURCE_DIR" ]; then
    echo "Error: Image source directory '$IMAGE_SOURCE_DIR' not found."
    exit 1
fi

# Process INPUT_IMAGE_TYPE to determine find patterns and ffmpeg extension
declare -a find_pattern_args # Declare as array
ffmpeg_input_ext=""
display_type_filter=""
user_input_type_upper="${INPUT_IMAGE_TYPE^^}" # Convert to uppercase for case matching

case "$user_input_type_upper" in
    JPG|JPEG)
        find_pattern_args=(-iname "*.jpg" -o -iname "*.jpeg")
        display_type_filter="*.jpg, *.jpeg"
        ffmpeg_input_ext="jpg" # Consistent extension for links and ffmpeg pattern
        ;;
    TIF|TIFF)
        find_pattern_args=(-iname "*.tif" -o -iname "*.tiff")
        display_type_filter="*.tif, *.tiff"
        ffmpeg_input_ext="tif"
        ;;
    PNG)
        find_pattern_args=(-iname "*.png")
        display_type_filter="*.png"
        ffmpeg_input_ext="png"
        ;;
    *)
        echo "Error: Unsupported or invalid image type '$INPUT_IMAGE_TYPE'."
        echo "Supported types (case-insensitive): JPG, JPEG, PNG, TIF, TIFF."
        display_help
        exit 1
        ;;
esac

ABS_IMAGE_SOURCE_DIR=$(realpath "$IMAGE_SOURCE_DIR")
if [[ "$OUTPUT_FILENAME" == */* ]]; then
    ABS_OUTPUT_FILE_DIR=$(dirname "$(realpath "$OUTPUT_FILENAME")")
    mkdir -p "$ABS_OUTPUT_FILE_DIR"
    FINAL_OUTPUT_PATH="$(realpath "$OUTPUT_FILENAME")"
else
    FINAL_OUTPUT_PATH="${INITIAL_PWD}/${OUTPUT_FILENAME}"
fi

echo "🎬 Starting video creation script..."
echo "   ----------------------------------"
echo "   Image Source Dir: $ABS_IMAGE_SOURCE_DIR"
echo "   Target Image Type: $user_input_type_upper (Searching for: $display_type_filter)"
echo "   Output File Path: $FINAL_OUTPUT_PATH"
echo "   Framerate:        $OUTPUT_FRAMERATE fps"
echo "   CRF Quality:      $VIDEO_QUALITY_CRF"
echo "   Encoder Preset:   $ENCODER_PRESET"
echo "   ----------------------------------"

TEMP_LINK_DIR=$(mktemp -d "${TARGET_DIR_PREFIX}_XXXXXX")
if [ ! -d "$TEMP_LINK_DIR" ]; then
    echo "Error: Could not create temporary directory."
    exit 1
fi
echo "   -Created temporary link directory: $TEMP_LINK_DIR"

cd "$TEMP_LINK_DIR" || { echo "Error: Could not navigate to $TEMP_LINK_DIR"; rm -rf "$TEMP_LINK_DIR"; exit 1; }

echo "   -Finding and symlinking images from '$ABS_IMAGE_SOURCE_DIR'..."

# Using \( ... \) for proper grouping of -o conditions in find
mapfile -t found_files < <(find "$ABS_IMAGE_SOURCE_DIR" -maxdepth 1 -type f \( "${find_pattern_args[@]}" \) | sort)

if [ ${#found_files[@]} -eq 0 ]; then
    echo "   ⚠️ WARNING: No files matching '$display_type_filter' (case-insensitive) were found in '$ABS_IMAGE_SOURCE_DIR'."
    cd "$INITIAL_PWD"
    rm -rf "$TEMP_LINK_DIR"
    echo "Script aborted."
    exit 1
fi

echo "   -Found ${#found_files[@]} image(s) matching pattern."

x=1
for original_filepath in "${found_files[@]}"; do
    counter_str=$(printf %04d "$x")
    # Symlink with the determined consistent extension (e.g., .jpg, .png, .tif)
    ln -s "$original_filepath" "img${counter_str}.${ffmpeg_input_ext}"
    x=$((x+1))
done
processed_file_count=$((x-1))
echo "   -Successfully symlinked $processed_file_count images in $TEMP_LINK_DIR as img%04d.${ffmpeg_input_ext}"

echo "   -Generating movie file with FFmpeg..."
ffmpeg_command=(
    ffmpeg -y -framerate "$OUTPUT_FRAMERATE" \
    -i "img%04d.${ffmpeg_input_ext}" \
    -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
    -c:v libx264 \
    -preset "$ENCODER_PRESET" \
    -crf "$VIDEO_QUALITY_CRF" \
    -tune stillimage \
    -pix_fmt yuv420p \
    -color_range 1 \
    -an \
    "$FINAL_OUTPUT_PATH"
)

echo "     Executing: ${ffmpeg_command[*]}"

if "${ffmpeg_command[@]}"; then
    echo "   ✅ Movie file generated successfully: $FINAL_OUTPUT_PATH"
else
    echo "   ❌ Error: FFmpeg command failed."
    echo "     Temporary files for debugging (if any) are in: '$TEMP_LINK_DIR'"
fi

echo "   -Cleaning up temporary directory: $TEMP_LINK_DIR"
cd "$INITIAL_PWD"
if [ -n "$TEMP_LINK_DIR" ] && [ -d "$TEMP_LINK_DIR" ]; then
    echo "     Removing $TEMP_LINK_DIR..."
    rm -rf "$TEMP_LINK_DIR"
    if [ -d "$TEMP_LINK_DIR" ]; then
        echo "     WARNING: Failed to remove temporary directory $TEMP_LINK_DIR. Manual cleanup may be required."
    else
        echo "     Successfully removed temporary directory $TEMP_LINK_DIR."
    fi
else
    if [ -n "$TEMP_LINK_DIR" ]; then
        echo "     INFO: Temporary directory $TEMP_LINK_DIR not found or already removed."
    else
        echo "     WARNING: Temporary directory variable was not set. No cleanup attempted."
    fi
fi

echo "🎉 Script complete!"

#END ALL