# Prediction interface for Cog ⚙️
# https://cog.run/python

import csv
import json
import os
import shutil
import tempfile
import os.path

from cog import BasePredictor, Input, Path


class Predictor(BasePredictor):
    def setup(self) -> None:
        """Load the model into memory to make running multiple predictions efficient"""
        # self.model = torch.load("./weights.pth")
        pass

    def predict(
        self,
        video: Path = Input(description="Video to quality assess"),
    ) -> str:

        # Make a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Copy the video to the temporary directory
                video_path = os.path.join(temp_dir, os.path.basename(video))
                print(f"Copying {video} to {video_path}")
                shutil.copy(video, video_path)
                tempcsv = os.path.join(temp_dir, "output.csv")

                os.system(
                    f"cd /DOVER ; python3 evaluate_a_set_of_videos.py --input_video_dir {temp_dir} --output_result_csv {tempcsv}"
                )
                lines = [r for r in csv.reader(open(tempcsv))]
                assert len(lines) == 2
                results = {k.strip(): float(v) for k, v in zip(lines[0], lines[1]) if k != "path"}
                return json.dumps(results)
            except:
                raise
            finally:
                # Delete the temporary directory
                shutil.rmtree(temp_dir)
