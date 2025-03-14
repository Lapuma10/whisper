import tkinter as tk
from tkinter import filedialog, ttk
import threading
import subprocess
import whisper
import os
import sys
from whisper.utils import get_writer
import time


def get_whisper_path():
    if getattr(sys, 'frozen', False):
        # Running inside a PyInstaller bundle
        return os.path.join(sys._MEIPASS, "whisper", "assets")
    else:
        # Running as a normal Python script
        return os.path.join(os.path.dirname(whisper.__file__), "assets")

# Force Whisper to load from the correct path
os.environ["WHISPER_ASSETS"] = get_whisper_path()
print("Using Whisper assets path:", os.environ["WHISPER_ASSETS"])

# Load Whisper model
model = whisper.load_model("large-v3")

# 📌 Automatically create 'Transcriptions' folder on Desktop
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "Transcriptions")
if not os.path.exists(desktop_path):
    os.makedirs(desktop_path)

# 📌 Function to avoid overwriting existing files
def get_unique_filename(base_path):
    """Returns a unique filename by appending _1, _2, etc., if the file already exists."""
    if not os.path.exists(base_path):
        return base_path

    base, ext = os.path.splitext(base_path)
    counter = 1
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
    return f"{base}_{counter}{ext}"

# 📌 Function to extract audio from video
def extract_and_split_audio(video_file, output_audio_template="segment_%03d.wav", segment_length=600):
    subprocess.run([
        'ffmpeg', '-i', video_file, '-ac', '1', '-ar', '44100', 
        '-f', 'segment', '-segment_time', str(segment_length),
        '-c:a', 'pcm_s16le', output_audio_template, '-y'
    ])

# 📌 Function to transcribe audio segments
def transcribe_audio_segments(progress, update_progress):
    segment_files = sorted([f for f in os.listdir() if f.startswith("segment_") and f.endswith(".wav")])
    srt_files = []

    for i, segment in enumerate(segment_files):
        result = model.transcribe(segment, language="no", word_timestamps=True)
        segment_srt_file = f"segment_{i:03d}.srt"
        
        srt_writer = get_writer("srt", ".")
        srt_writer(result, segment, {"max_words_per_line": 6})
        srt_files.append(segment_srt_file)
        
        update_progress(50 + (i + 1) / len(segment_files) * 40)  # Smoothly update progress

    return srt_files

# 📌 Function to combine SRT files
def combine_srt_files(srt_files, output_file):
    with open(output_file, "w") as outfile:
        for srt_file in srt_files:
            with open(srt_file) as infile:
                outfile.write(infile.read())
                outfile.write("\n")

    # Cleanup segment SRT files
    for srt_file in srt_files:
        os.remove(srt_file)

# 📌 Function to animate "Transcribing..." dots
def animate_dots():
    dots = ["", ".", "..", "..."]
    count = 0
    while transcribing.get():
        result_label.config(text=f"Transcribing{dots[count % 4]}")
        count += 1
        time.sleep(0.5)
        window.update_idletasks()

# 📌 Function to process video file
def process_video(video_file):
    transcribing.set(True)
    threading.Thread(target=animate_dots, daemon=True).start()

    # Generate unique filename inside 'Transcriptions' folder
    base_filename = os.path.splitext(os.path.basename(video_file))[0] + ".srt"
    output_srt = get_unique_filename(os.path.join(desktop_path, base_filename))
    
    result_label.config(text="Extracting audio...")
    update_progress(10)

    extract_and_split_audio(video_file)
    
    result_label.config(text="Transcribing...")
    srt_files = transcribe_audio_segments(progress, update_progress)

    result_label.config(text="Combining subtitles...")
    combine_srt_files(srt_files, output_srt)

    update_progress(100)
    transcribing.set(False)  # Stop animation
    result_label.config(text="Transcription complete!")

    # Enable "Open Transcription Location" button
    open_file_button.config(state="normal", command=lambda: open_file_location(output_srt))

# 📌 Function to open file location in Finder/Explorer
def open_file_location(file_path):
    """Opens Finder/Explorer with the file selected."""
    try:
        if sys.platform == "darwin":  # macOS
            subprocess.run(["open", "-R", file_path])  # Reveals file in Finder
        elif sys.platform == "win32":  # Windows
            subprocess.run(["explorer", "/select,", file_path], shell=True)  # Selects file in Explorer
        elif sys.platform == "linux":  # Linux
            subprocess.run(["xdg-open", os.path.dirname(file_path)])  # Opens folder (Linux has no native file selection)
    except Exception as e:
        result_label.config(text=f"Error opening file location: {e}")

# 📌 Function to upload and process video
def upload_video():
    video_file = filedialog.askopenfilename(filetypes=[("Video/Audio Files", "*.mov *.mp4 *.m4a *.mp3 *.wav")])
    if video_file:
        result_label.config(text="Processing video...")
        progress.set(0)
        open_file_button.config(state="disabled")  # Disable button until done
        threading.Thread(target=process_video, args=(video_file,), daemon=True).start()

# 📌 Function to update progress bar
def update_progress(value):
    progress.set(value)
    window.update_idletasks()

# 📌 GUI Setup
window = tk.Tk()
window.title("Whisper Transcriber")
window.geometry("600x400")

# Track animation state
transcribing = tk.BooleanVar()
transcribing.set(False)

# Upload Button
upload_button = tk.Button(window, text="Select a Video", command=upload_video)
upload_button.pack(pady=20)

# Progress Bar
progress = tk.DoubleVar()
progress_bar = ttk.Progressbar(window, variable=progress, maximum=100)
progress_bar.pack(pady=20)

# Result Label
result_label = tk.Label(window, text="Select a video to transcribe.", wraplength=500)
result_label.pack(pady=10)

# Open Transcription Location Button (Disabled initially)
open_file_button = tk.Button(window, text="Open Transcription Location", state="disabled")
open_file_button.pack(pady=20)

# Start GUI
window.mainloop()
