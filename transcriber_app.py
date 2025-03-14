import tkinter as tk
from tkinter import filedialog, ttk
import subprocess
import whisper
import os
from whisper.utils import get_writer
import sys

# Function to extract and split audio from the video file
def extract_and_split_audio(video_file, output_audio_template="segment_%03d.wav", segment_length=600):
    # Converts audio to WAV format with single channel (mono) and sample rate of 44100 Hz
    subprocess.run([
        'ffmpeg', '-i', video_file, '-ac', '1', '-ar', '44100', 
        '-f', 'segment', '-segment_time', str(segment_length),
        '-c:a', 'pcm_s16le', output_audio_template, '-y'
    ])

# Function to transcribe each segment
def transcribe_audio_segments():
    model = whisper.load_model("large-v3")
    segment_files = sorted([f for f in os.listdir() if f.startswith("segment_") and f.endswith(".wav")])
    srt_files = []

    for i, segment in enumerate(segment_files):
        # Update progress for each segment
        progress.set((i + 1) / len(segment_files) * 50)  # Transcription stage progress
        window.update_idletasks()
        
        result = model.transcribe(segment, language="no", word_timestamps=True)
        segment_srt_file = f"segment_{i:03d}.srt"
        
        # Use Whisper's get_writer to write the SRT file with max_words_per_line
        srt_writer = get_writer("srt", ".")
        srt_writer(result, segment, {"max_words_per_line": 6})
        srt_files.append(segment_srt_file)
        
    return srt_files

# Function to combine SRT files
def combine_srt_files(srt_files, combined_file="transcription_combined.srt"):
    with open(combined_file, "w") as outfile:
        for srt_file in srt_files:
            with open(srt_file) as infile:
                outfile.write(infile.read())
                outfile.write("\n")  # Separate each file content with a newline for clarity

    # Clean up segment SRT files after combining
    for srt_file in srt_files:
        os.remove(srt_file)

def upload_video():
    video_file = filedialog.askopenfilename(filetypes=[("Video/Audio Files", "*.mov *.mp4 *.m4a")])
    if video_file:
        # Step 1: Extract and split audio into segments
        result_label.config(text="Extracting audio from video...")
        progress.set(10)
        window.update_idletasks()
        extract_and_split_audio(video_file)
        
        # Step 2: Transcribe each audio segment
        result_label.config(text="Transcribing audio...")
        srt_files = transcribe_audio_segments()

        # Step 3: Combine all individual SRT files into one
        result_label.config(text="Combining SRT files...")
        combined_srt_file = "transcription_combined.srt"
        combine_srt_files(srt_files, combined_file=combined_srt_file)

        # Update progress and notify user
        progress.set(100)
        result_label.config(text="Transcription complete!")
        download_button.config(state="normal", command=lambda: download_srt(combined_srt_file))

# Function to download the SRT file
def download_srt(subtitle_file):
    # Ensure the file exists before trying to open it
    if os.path.exists(subtitle_file):
        try:
            # Platform-specific file opening
            if sys.platform == "darwin":  # macOS
                subprocess.call(["open", subtitle_file])
            elif sys.platform == "win32":  # Windows
                subprocess.call(["start", subtitle_file], shell=True)
            elif sys.platform == "linux":  # Linux
                subprocess.call(["xdg-open", subtitle_file])
        except Exception as e:
            result_label.config(text=f"Error opening file: {e}")
    else:
        result_label.config(text="SRT file not found.")

# GUI Setup
window = tk.Tk()
window.title("Video Transcription App")
window.geometry("600x400")

# Button to upload video
upload_button = tk.Button(window, text="Upload Video", command=upload_video)
upload_button.pack(pady=20)

# Progress bar
progress = tk.DoubleVar()
progress_bar = ttk.Progressbar(window, variable=progress, maximum=100)
progress_bar.pack(pady=20)

# Result label
result_label = tk.Label(window, text="Waiting for video file...", wraplength=500)
result_label.pack(pady=10)

# Button to download .srt file (disabled initially)
download_button = tk.Button(window, text="Download .srt", state="disabled")
download_button.pack(pady=20)

window.mainloop()
