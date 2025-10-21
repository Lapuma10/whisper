import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import whisper
import os
import sys
import threading
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
        self.window.title("Norwegian Whisper Transcriber")
        self.window.geometry("600x400")
        
        self.model = None
        self.current_output_file = None
        self.processing_thread = None
        self.canceled = False
        
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
        # Main frame with padding
        main_frame = tk.Frame(self.window, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="Norwegian Audio Transcriber",
            font=("Helvetica", 16)
        )
        title_label.pack(pady=(0, 20))
        
        # Upload Button
        self.upload_button = tk.Button(
            main_frame, 
            text="Select Audio/Video File",
            font=("Helvetica", 12),
            command=self.upload_video,
            width=20,
            height=2
        )
        self.upload_button.pack(pady=15)
        
        # Progress Bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            length=500,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(pady=15, fill=tk.X)
        
        # Status Label
        self.status_var = tk.StringVar(value="Ready to transcribe")
        self.status_label = tk.Label(
            main_frame,
            textvariable=self.status_var,
            wraplength=550,
            justify=tk.LEFT,
            font=("Helvetica", 10)
        )
        self.status_label.pack(pady=10, fill=tk.X)
        
        # Button Frame
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=15)
        
        # Cancel Button
        self.cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            font=("Helvetica", 10),
            command=self.cancel_processing,
            state="disabled",
            width=12
        )
        self.cancel_button.pack(side=tk.LEFT, padx=10)
        
        # Open Location Button
        self.open_file_button = tk.Button(
            button_frame,
            text="Open Transcription",
            font=("Helvetica", 10),
            command=self.open_current_file_location,
            state="disabled",
            width=18
        )
        self.open_file_button.pack(side=tk.LEFT, padx=10)
    
    def update_status(self, message):
        """Update status label safely from any thread"""
        def _update():
            self.status_var.set(message)
            self.window.update_idletasks()  # Force update
        
        # Schedule the update on the main thread
        self.window.after(0, _update)
        logging.info(message)
    
    def update_progress(self, value):
        """Update progress bar safely from any thread"""
        def _update():
            self.progress_var.set(value)
            self.window.update_idletasks()  # Force update
            logging.info(f"Progress updated to {value}%")
        
        # Schedule the update on the main thread
        self.window.after(0, _update)

    def update_button_states(self, upload_state="normal", cancel_state="disabled", open_state="disabled"):
        """Update all button states safely from any thread"""
        def _update():
            self.upload_button.config(state=upload_state)
            self.cancel_button.config(state=cancel_state)
            self.open_file_button.config(state=open_state)
            self.window.update_idletasks()  # Force update
        
        # Schedule the update on the main thread
        self.window.after(0, _update)
    
    def cancel_processing(self):
        """Cancel the current processing operation"""
        if messagebox.askyesno("Cancel", "Are you sure you want to cancel the transcription?"):
            self.canceled = True
            self.update_status("Canceling transcription...")
    
    def upload_video(self):
        """Handle video selection and processing"""
        video_file = filedialog.askopenfilename(
            title="Select Audio/Video File",
            filetypes=[
                ("Audio/Video Files", "*.mov *.mp4 *.m4a *.mp3 *.wav *.avi *.mkv"),
                ("All Files", "*.*")
            ]
        )
        if not video_file:
            return
        
        # Reset UI state
        self.canceled = False
        self.update_progress(0)
        self.update_status(f"Processing: {os.path.basename(video_file)}...")
        self.update_button_states(upload_state="disabled", cancel_state="normal", open_state="disabled")
        
        # Start the transcription thread
        self.processing_thread = threading.Thread(
            target=self.process_video_thread,
            args=(video_file,),
            daemon=True
        )
        self.processing_thread.start()
        
        # Check thread status periodically
        self.window.after(100, self.check_progress)
    
    def check_progress(self):
        """Check if the processing thread is still running"""
        if self.processing_thread and self.processing_thread.is_alive():
            # Still running, check again soon
            self.window.update_idletasks()  # Force UI updates
            self.window.after(100, self.check_progress)
        else:
            # Thread has finished or was canceled
            if self.canceled:
                self.update_status("Transcription canceled.")
                self.update_button_states(upload_state="normal", cancel_state="disabled", open_state="disabled")
            elif self.current_output_file and os.path.exists(self.current_output_file):
                self.update_status("Transcription complete!")
                self.update_button_states(upload_state="normal", cancel_state="disabled", open_state="normal")
            else:
                # This shouldn't happen if everything went well
                self.update_status("Transcription failed or no output file was created.")
                self.update_button_states(upload_state="normal", cancel_state="disabled", open_state="disabled")
    
    def process_video_thread(self, video_file):
        """Process video in a separate thread"""
        try:
            # Load model
            if not self.model:
                self.update_status("Loading Whisper model (large-v3)...")
                self.update_progress(5)
                self.model = whisper.load_model("large-v3")
                self.update_status("Large-v3 model loaded successfully")
                self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
            
            if self.canceled:
                return
            
            # Set up output file
            base_filename = os.path.splitext(os.path.basename(video_file))[0] + ".srt"
            output_srt = self.get_unique_filename(os.path.join(self.desktop_path, base_filename))
            self.current_output_file = output_srt
            
            # Extract audio
            self.update_status("Extracting audio...")
            self.update_progress(10)
            self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
            
            if self.canceled:
                return
                
            self.extract_and_split_audio(video_file)
            
            if self.canceled:
                return
                
            # Transcribe
            self.update_status("Transcribing audio...")
            self.update_progress(20)
            self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
            srt_files = self.transcribe_audio_segments()
            
            if self.canceled or not srt_files:
                return
                
            self.update_status("Combining subtitles...")
            self.update_progress(90)
            self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
            self.combine_srt_files(srt_files, output_srt)
            
            # Verify the output file exists
            if os.path.exists(output_srt):
                self.update_status(f"Transcription saved: {os.path.basename(output_srt)}")
                self.update_progress(100)
                self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
            else:
                self.update_status("Error: Output file was not created")
        
        except Exception as e:
            logging.error(f"Error during processing: {e}")
            self.update_status(f"Error: {str(e)}")
            self.window.after(0, lambda: messagebox.showerror("Error", str(e)))
    
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
            if self.canceled:
                return []
                
            try:
                # Calculate progress (20-90% range for transcription)
                progress = 20 + ((i + 1) / len(segment_files) * 70)
                self.update_progress(int(progress))  # Convert to integer for cleaner logging
                self.update_status(f"Transcribing segment {i+1}/{len(segment_files)}")
                self.window.after(0, lambda: self.window.update_idletasks())  # Force UI update
                
                # Always use Norwegian language
                result = self.model.transcribe(segment, language="no", task="transcribe", word_timestamps=True)
                
                segment_srt_file = f"segment_{i:03d}.srt"
                srt_writer = get_writer("srt", ".")
                srt_writer(result, segment, {"max_words_per_line": 2})
                srt_files.append(segment_srt_file)
                
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
        
        # Also clean up WAV files
        for wav_file in [f for f in os.listdir() if f.startswith("segment_") and f.endswith(".wav")]:
            try:
                os.remove(wav_file)
                logging.info(f"Removed temporary file: {wav_file}")
            except OSError as e:
                logging.warning(f"Could not remove temporary file {wav_file}: {e}")
    
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
