# Singleton class for Layout Model from Paddle
from io import BytesIO
import numpy as np
from paddlex import create_model
from PIL import Image
import os
import psycopg2
import requests

class LayoutModel:
    _instance = None

    def __init__(self, cursor, lecture_name, video_id, model_name="PP-DocLayout_plus-L"):
        self.lecture_name = lecture_name
        self.video_id = video_id
        self.model = self.get_instance(model_name)
        self.frames_with_raw_boxes = []  # list[dict]
        self.frame_data = self.get_frame_data(cursor)

    @classmethod
    def get_instance(cls, model_name="PP-DocLayout_plus-L"):
        if cls._instance is None:
            cls._instance = create_model(model_name=model_name)
        return cls._instance
    

    def get_frame_data(self, cursor):
        # get all path values from the table frames at variable path
        sql = """
            SELECT frame_index, path, height, width
            FROM frames
            WHERE lecture_name = %s AND video_id = %s
        """        
        try:
            cursor.execute(sql, (self.lecture_name, self.video_id))
            result = cursor.fetchall()

            frames_list = [
                {
                    "frame_index": frame_index, 
                    "path": path,
                    "height": height,
                    "width": width  
                }
                for frame_index, path, height, width in result
            ]

        except psycopg2.Error as e:
            print(f"Query failed: {e}")
            cursor.connection.rollback()
    
        return frames_list

    # input: path to the one frame/slide that's currently depicted
    def run_and_collect(self, frame_path, frame_index, frame_height, frame_width):                 
        
        response = requests.get(frame_path)
        img = Image.open(BytesIO(response.content)).convert("RGB")
        img_np = np.array(img)

        try:
            prediction = self.model.predict(
                img_np,
                layout_nms=True,
                threshold= {2: 0.4, 10: 0.45, 12: 0.45},
                layout_merge_bboxes_mode="large",
            )
        except Exception as e:
            print("Error while predicting:", e)

        res = self.frame_postprocessing(prediction)

        frame_entry = {
            "frame_index": frame_index, 
            "frame_width": frame_width,
            "frame_height": frame_height,
            "boxes": []
            }

        for box in res['boxes']:
            
            x1, y1, x2, y2 = map(float, box["coordinate"])
            frame_entry['boxes'].append({
                "lecture_name": self.lecture_name,
                "video_id": self.video_id,
                "box_id": box["box_id"],
                "score": box["score"],
                "label": box["label"],
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                })
        
        self.frames_with_raw_boxes.append(frame_entry)

        return res
    

    def run_and_store_all_frames(self, cursor):
        
        for frame in self.frame_data:

            if not (frame['path'].startswith("http") or os.path.isfile(frame['path'])):
                continue

            try:
                self.run_and_collect(frame['path'], frame['frame_index'], frame['height'], frame['width'])
            except Exception as e:
                print(f"Error processing {frame['path']}: {e}")
        
        
        self.postprocess_and_store(cursor, repeat_threshold=0.7, sim_threshold=0.01)


    def indentation_grouping(self, sorted_boxes, indent_threshold, allowed_labels):
        grouped_boxes = []
        current_group = None
        current_xmin = None  # Track minimum x of current group
        group_scores = []

        for box in sorted_boxes:
            box_id = box['box_id']
            label = box['label']
            xmin = box['x1']
            ymin = box['y1']
            xmax = box['x2']
            ymax = box['y2']
            score = box['score']

            if label in ["text", "paragraph_title"]:
                if current_group is None:
                    # Start new group
                    current_group = {
                        'box_id': box_id,
                        'cls_id': 2,
                        'label': "text",
                        'coordinate': [xmin, ymin, xmax, ymax]
                    }
                    group_scores = [score]
                    current_xmin = xmin
                else:
                    if xmin > current_xmin + indent_threshold:
                        # Still part of same group (indented)
                        group_coords = current_group['coordinate']
                        group_coords[0] = min(group_coords[0], xmin)
                        group_coords[1] = min(group_coords[1], ymin)
                        group_coords[2] = max(group_coords[2], xmax)
                        group_coords[3] = max(group_coords[3], ymax)

                        group_scores.append(score)
                    else:
                        # Finalize previous group
                        current_group['score'] = min(group_scores)
                        grouped_boxes.append(current_group)

                        # Start new group
                        current_group = {
                            'box_id': box_id,
                            'cls_id': 2,
                            'label': "text",
                            'coordinate': [xmin, ymin, xmax, ymax]
                        }
                        current_xmin = xmin
                        group_scores = [score]

            elif label == "formula":
                # Always add formula to current group (if any)
                if current_group is not None:
                    group_coords = current_group['coordinate']
                    group_coords[0] = min(group_coords[0], xmin)
                    group_coords[1] = min(group_coords[1], ymin)
                    group_coords[2] = max(group_coords[2], xmax)
                    group_coords[3] = max(group_coords[3], ymax)

                    group_scores.append(score)

                # Also add the formula as a standalone box
                grouped_boxes.append({
                    **box,
                    "coordinate": [box['x1'], box['y1'], box['x2'], box['y2']]
                })

            elif label in allowed_labels:
                # Finalize group if active
                if current_group is not None:
                    current_group['score'] = min(group_scores)
                    grouped_boxes.append(current_group)
                    current_group = None
                    current_xmin = None
                    group_scores = []

                # Add the unrelated box as-is
                grouped_boxes.append({
                    **box,
                    "coordinate": [box['x1'], box['y1'], box['x2'], box['y2']]
                })

        # Final group at end
        if current_group is not None:
            current_group['score'] = min(group_scores)
            grouped_boxes.append(current_group)

        for index, box in enumerate(grouped_boxes):
            print(index, box['box_id'])
        return grouped_boxes
    

    def add_IDs(self, sorted_boxes):
        for idx, box in enumerate(sorted_boxes):
            box["box_id"] = idx
        return sorted_boxes

    def postprocess_and_store(self, cursor, repeat_threshold = 0.7, sim_threshold= 0.01, allowed_labels = None):
        """
        Filters out repetitive boxes across frames and inserts the remaining ones into `layouts`.
        """
        if allowed_labels is None:
            allowed_labels = ["header", "doc_title", "formula", "text", "table", "paragraph_title", "image", "title"]

        if not self.frames_with_raw_boxes:
            return

        boxes_to_del = set()
        title_boxes = set()

        if len(self.frames_with_raw_boxes) >= 3:

            for frame in self.frames_with_raw_boxes:
                for box in frame['boxes']:

                    # if this box has not already been sorted out
                    if (frame['frame_index'], box['box_id']) not in boxes_to_del:

                        # get sim_threshold pixel value
                        x_variance = frame['frame_width'] * sim_threshold
                        y_variance = frame['frame_height'] * sim_threshold

                        sim_boxes = {(frame['frame_index'], box['box_id'])}
                        labels = [box['label']]

                        for compare_frame in self.frames_with_raw_boxes:
                            
                            if frame != compare_frame and frame['frame_width'] == compare_frame['frame_width'] and frame['frame_height'] == compare_frame['frame_height']:
                                
                                for compare_box in compare_frame['boxes']:
                                    if (compare_frame['frame_index'], compare_box['box_id']) not in boxes_to_del:

                                        # x2 not of interest because title boxes may have different widths                                    
                                        x1_equal = abs(box['x1'] - compare_box['x1']) <= x_variance
                                        y1_equal = abs(box['y1'] - compare_box['y1']) <= y_variance
                                        y2_equal = abs(box['y2'] - compare_box['y2']) <= y_variance

                                        if x1_equal and y1_equal and y2_equal:
                                            sim_boxes.add((compare_frame['frame_index'], compare_box['box_id']))
                                            labels.append(compare_box['label'])
                                            break
                        
                        # if a repetetive box is labeled paragraph_title or doc_title, we can assume that it's the title of the slide
                        title_count = sum(1 for label in labels if label in {"paragraph_title", "doc_title"})
                            
                        if len(sim_boxes) >= len(self.frames_with_raw_boxes) * repeat_threshold:
                            if title_count / len(sim_boxes) >= 0.8:
                                title_boxes.update(sim_boxes)
                            else:
                                # Delete the boxes as before
                                boxes_to_del.update(sim_boxes)

            

        for frame in self.frames_with_raw_boxes:
            
            grouped_boxes = None
            
            if len(self.frames_with_raw_boxes) >= 3:
                frame['boxes'] = [
                    {**box, 'label': 'title'} if (frame['frame_index'], box['box_id']) in title_boxes else box
                    for box in frame['boxes'] if (frame['frame_index'], box['box_id']) not in boxes_to_del
                ]
                       
                grouped_boxes = self.indentation_grouping(frame['boxes'], 0.02 * frame['frame_width'], allowed_labels)
     
            sql = """
                INSERT INTO layouts
                    (lecture_name, video_id, frame_index, box_id, label, x1, y1, x2, y2)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lecture_name, video_id, frame_index, box_id) DO NOTHING
            """

            if grouped_boxes is None:
                final_boxes = frame['boxes']
            else:
                for box in grouped_boxes:
                    box["x1"], box["y1"], box["x2"], box["y2"] = box["coordinate"]
                    # Optionally remove the old "coordinate" key
                    del box["coordinate"]
                final_boxes = grouped_boxes

            for b in final_boxes:
                try:
                    cursor.execute(
                        sql, 
                        (
                            self.lecture_name, 
                            self.video_id, 
                            frame['frame_index'], 
                            b['box_id'],
                            b['label'],
                            b['x1'], b['y1'], b['x2'], b['y2']
                        )
                    )
                except Exception as e:
                    cursor.connection.rollback()
                    print(f"[layouts] insert error on frame {frame['frame_index']}, box {box['box_id']}: {e}")
           
        return

    def frame_postprocessing(self, prediction):

        res_dict = next(prediction)                # prediction at index 0 - generator type

        sorted_boxes = sorted(
            res_dict['boxes'],
            key=lambda box: box['coordinate'][1]  # Sort by Y-top value - top-down
        )

        # res_dict['boxes'] = self.indentation_grouping(sorted_boxes, 0.03 * frame_width, allowed_labels)      # threshold of indentation: 5% of the width of the whole slide
        res_dict['boxes'] = self.add_IDs(sorted_boxes)

        print("res_dict modified: ", res_dict)

        return res_dict
        
    