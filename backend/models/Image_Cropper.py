import json
import os
from pathlib import Path
from PIL import Image

class ImageCropper:
    def __init__(self, image_path: str, json_path: str, frame: int):
        self.image_path = Path(image_path)
        self.json_path = Path(json_path)
        self.frame = frame

        # Load the image
        self.image = Image.open(self.image_path).convert("RGB")

        # Load layout JSON
        with open(self.json_path, "r", encoding="utf-8") as f:
            self.layout_data = json.load(f)

        # Extract box coordinates from the 'boxes' field
        self.boxes = [box["coordinate"] for box in self.layout_data.get("boxes", [])]

    
    def crop_box(self, index: int) -> str:
        if index < 0 or index >= len(self.boxes):
            raise IndexError(f"Box index {index} out of range. Total boxes: {len(self.boxes)}")

        x1, y1, x2, y2 = self.boxes[index]
        cropped = self.image.crop((x1, y1, x2, y2))

        # Save to temp file
        output_dir = "./temp_crops"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"crop_{self.frame}_box{index}.png")
        cropped.save(output_path)

        return output_path

    def get_all_boxes(self):
        return self.boxes
