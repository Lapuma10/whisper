import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import whisper
import os
import sys
from whisper.utils import get_writer
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class TranscriberApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Whisper Transcriber")
        self.window.geometry("600x400")
        
        self.model = None
        self.current_output_file = None
        
        # Set up paths
        if getattr(sys, 'frozen', False):
            whisper_path = os.path.join(sys._MEIPASS, "whisper", "assets")
        else:
            import site
            site_packages = site.getsitepackages()[0]
            whisper_path = os.path.join(site_packages, "whisper", "assets")
        
        os.environ["WHISPER_ASSETS"] = whisper_path
        logging.info("Using Whisper assets path: " + os.environ["WHISPER_ASSETS"])
        
        # Create output directory
        self.desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "Transcriptions")
        os.makedirs(self.desktop_path, exist_ok=True)
        logging.info(f"Output directory: {self.desktop_path}")
        
        self.setup_gui()
    
    def setup_gui(self):
        # Upload Button
        self.upload_button = tk.Button(
            self.window, 
            text="Select a Video", 
            command=self.upload_video
        )
        self.upload_button.pack(pady=20)
        
        # Progress Bar
        self.progress = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            self.window, 
            variable=self.progress, 
            maximum=100
        )
        self.progress_bar.pack(pady=20)
        
        # Result Label
        self.result_label = tk.Label(
            self.window, 
            text="Select a video to transcribe.", 
            wraplength=500
        )
        self.result_label.pack(pady=10)
        
        # Open Location Button
        self.open_file_button = tk.Button(
            self.window, 
            text="Open Transcription Location", 
            state="disabled",
            command=self.open_current_file_location
        )
        self.open_file_button.pack(pady=20)
    
    def update_status(self, message):
        """Update status label and log message"""
        self.result_label.config(text=message)
        logging.info(message)
        self.window.update()
    
    def update_progress(self, value):
        """Update progress bar"""
        self.progress.set(value)
        self.window.update()
        logging.info(f"Progress: {value}%")
    
    def upload_video(self):
        """Handle video selection and processing"""
        video_file = filedialog.askopenfilename(
            filetypes=[("Video/Audio Files", "*.mov *.mp4 *.m4a *.mp3 *.wav")]
        )
        if not video_file:
            return
            
        self.update_status(f"Selected file: {video_file}")
        self.update_status("Processing video...")
        self.progress.set(0)
        self.open_file_button.config(state="disabled")
        
        try:
            self.process_video(video_file)
        except Exception as e:
            self.update_status(f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))
    
    def process_video(self, video_file):
        """Process video without threading"""
        # Load model
        if not self.model:
            self.update_status("Loading Whisper model (large-v3)...")
            self.model = whisper.load_model("large-v3")
            self.update_status("Large-v3 model loaded successfully")
        
        # Set up output file
        base_filename = os.path.splitext(os.path.basename(video_file))[0] + ".srt"
        output_srt = self.get_unique_filename(os.path.join(self.desktop_path, base_filename))
        self.current_output_file = output_srt
        
        # Extract audio
        self.update_status("Extracting audio...")
        self.update_progress(10)
        self.extract_and_split_audio(video_file)
        
        # Transcribe
        self.update_status("Transcribing...")
        srt_files = self.transcribe_audio_segments()
        
        if srt_files:
            self.update_status("Combining subtitles...")
            self.combine_srt_files(srt_files, output_srt)
            
            # Verify the output file exists
            if os.path.exists(output_srt):
                self.update_status(f"Output file created: {output_srt}")
                self.update_progress(100)
                self.update_status("Transcription complete!")
                self.open_file_button.config(state="normal")
            else:
                self.update_status("Error: Output file was not created")
        else:
            self.update_status("Transcription failed.")
    
    def extract_and_split_audio(self, video_file, output_audio_template="segment_%03d.wav", segment_length=600):
        """Extract and split audio from video"""
        try:
            # Run FFmpeg
            cmd = [
                'ffmpeg', '-v', 'error',
                '-i', video_file,
                '-ac', '1',
                '-ar', '44100',
                '-f', 'segment',
                '-segment_time', str(segment_length),
                '-c:a', 'pcm_s16le',
                output_audio_template,
                '-y'
            ]
            
            logging.info("Executing FFmpeg command: " + ' '.join(cmd))
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Verify output files were created
            output_files = [f for f in os.listdir() if f.startswith("segment_") and f.endswith(".wav")]
            if not output_files:
                raise Exception("No output files were created by FFmpeg")
            logging.info(f"Created {len(output_files)} audio segments")
            
        except subprocess.CalledProcessError as e:
            logging.error("FFmpeg error output: " + e.stderr)
            raise Exception(f"FFmpeg error: {e.stderr}")
        except Exception as e:
            logging.error(f"Error running FFmpeg: {str(e)}")
            raise
    
    def transcribe_audio_segments(self):
        """Transcribe all audio segments"""
        segment_files = sorted([f for f in os.listdir() if f.startswith("segment_") and f.endswith(".wav")])
        logging.info(f"Found {len(segment_files)} audio segments to transcribe")
        srt_files = []
        
        for i, segment in enumerate(segment_files):
            try:
                logging.info(f"Transcribing segment {i+1}/{len(segment_files)}: {segment}")
                # Always use Norwegian language
                result = self.model.transcribe(segment, language="no", task="transcribe", word_timestamps=True)
                
                segment_srt_file = f"segment_{i:03d}.srt"
                srt_writer = get_writer("srt", ".")
                srt_writer(result, segment, {"max_words_per_line": 6})
                srt_files.append(segment_srt_file)
                
                self.update_progress(50 + (i + 1) / len(segment_files) * 40)
            except Exception as e:
                logging.error(f"Error transcribing segment {segment}: {e}")
                continue
        
        return srt_files
    
    def combine_srt_files(self, srt_files, output_file):
        """Combine all SRT files into one output file"""
        logging.info(f"Combining {len(srt_files)} SRT files into {output_file}")
        with open(output_file, "w") as outfile:
            for srt_file in srt_files:
                with open(srt_file) as infile:
                    outfile.write(infile.read())
                    outfile.write("\n")
        
        # Cleanup segment files
        for srt_file in srt_files:
            try:
                os.remove(srt_file)
                logging.info(f"Removed temporary file: {srt_file}")
            except OSError as e:
                logging.warning(f"Could not remove temporary file {srt_file}: {e}")
    
    def get_unique_filename(self, base_path):
        """Get a unique filename by appending a counter if file exists"""
        if not os.path.exists(base_path):
            return base_path
        
        base, ext = os.path.splitext(base_path)
        counter = 1
        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1
        return f"{base}_{counter}{ext}"
    
    def open_current_file_location(self):
        """Open the folder containing the current output file"""
        if self.current_output_file and os.path.exists(self.current_output_file):
            try:
                logging.info(f"Opening location for file: {self.current_output_file}")
                if sys.platform == "darwin":  # macOS
                    subprocess.run(["open", "-R", self.current_output_file])
                elif sys.platform == "win32":  # Windows
                    subprocess.run(["explorer", "/select,", self.current_output_file], shell=True)
                else:  # Linux
                    subprocess.run(["xdg-open", os.path.dirname(self.current_output_file)])
            except Exception as e:
                logging.error(f"Error opening file location: {e}")
                messagebox.showerror("Error", f"Could not open file location: {e}")
        else:
            logging.warning("No valid output file available")
            messagebox.showerror("Error", "No valid output file available")
    
    def run(self):
        """Run the application"""
        self.window.mainloop()

if __name__ == "__main__":
    app = TranscriberApp()
    app.run()
