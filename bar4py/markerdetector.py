import cv2
import numpy as np
from shortfuncs import *
from marker import Marker

# MarkerDetector

class MarkerDetector:
    def __init__(self, dictionary=None,
                 camera_matrix=None, dist_coeffs=None):
        self.dictionary = dictionary
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs

    def isProbableMarker(self, approx_curve, limit=32):
        if approx_curve.shape != (4,1,2): return False
        if (min(np.sum((approx_curve[0] - approx_curve[2])**2),
                np.sum((approx_curve[1] - approx_curve[3])**2))
            >= limit**2): return True

    def localRect(self, corners):
        x0, y0 = corners[:,1].min(), corners[:,0].min()
        x1, y1 = corners[:,1].max(), corners[:,0].max()
        return np.array([x0, y0, x1, y1], dtype='uint32').reshape(2,2)

    def localFrame(self, rect, frame):
        return frame[rect[0,0]:rect[1,0], rect[0,1]:rect[1,1]]

    def localCorners(self, rect, corners):
        local_corners = np.zeros((4,2), dtype=corners.dtype)
        local_corners[:,0] = corners[:,0] - rect[0,1]
        local_corners[:,1] = corners[:,1] - rect[0,0]
        return local_corners

    def recognize(self, points, frame, dictionary=None, limit=0.85, side_length=42):
        dictionary = dictionary or self.dictionary
        if dictionary is None: raise TypeError('recognize nead dictionary')

        # To Gray
        gray = frame
        if len(gray.shape) == 3: gray = bgr2gray(frame)

        # Convert the points, gray to local_points, local_gray
        rect = self.localRect(points)
        gray = self.localFrame(rect, gray)
        points = self.localCorners(rect, points)

        # Define src_points and dst_points, src: 0,1,2,3 -> dst: 1,0,3,2
        points_src = np.float32(points)
        points_dst = np.float32([[0,side_length],[0,0], 
                                 [side_length,0],[side_length,side_length]])
    

        # Calc transform matrix and perspective dst map
        M = cv2.getPerspectiveTransform(points_src, points_dst)
        dst = cv2.warpPerspective(gray, M, (side_length, side_length))

        # Begin recognize
        _, dst = cv2.threshold(dst, dst.mean(), 1, cv2.THRESH_OTSU)
        for marker_id, hash_map in dictionary:
            hash_map = cv2.resize(bgr2gray(hash_map), (side_length, side_length))
            _, hash_map = cv2.threshold(hash_map, hash_map.mean(), 1, cv2.THRESH_OTSU)
            deviation = rotations = 0
            for i in range(4):
                now_deviation = np.sum((dst == hash_map).astype(int)) / (side_length**2)
                if now_deviation > deviation: deviation, rotations = now_deviation, i
                hash_map = np.rot90(hash_map)
            if deviation > limit:
                # # For debug
                # cv2.imshow('dst', np.rot90(dst, -rotations)*255)
                # print(deviation)
                return marker_id, rotations

    def detect(self, frame, epsilon_rate=0.01, en_debug=False):
        # Output marker list
        markers = []

        # To Gray
        gray = frame
        if len(gray.shape) == 3: gray = bgr2gray(frame)

        # Thresh
        ret, thresh = cv2.threshold(gray, gray.mean(), 255,
                                    cv2.THRESH_BINARY)
        if not ret: return False

        # Find contours
        _, contours, _ = cv2.findContours(thresh, cv2.RETR_LIST,
                                          cv2.CHAIN_APPROX_NONE)

        # Probable Marker
        _markers = []
        for cnt in contours:
            epsilon = epsilon_rate * cv2.arcLength(cnt,True)
            approx_curve = cv2.approxPolyDP(cnt,epsilon,True)
            if self.isProbableMarker(approx_curve):
                points = approx_curve.reshape(4,2)
                corners = np.float32([points[1], points[0], points[2], points[3]])
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1)
                corners = cv2.cornerSubPix(gray, corners, (5,5), (-1,-1), criteria)
                _markers.append(Marker(points=points, corners=corners))

        # Matched Marker
        if self.dictionary:
            for marker in _markers:
                rst = self.recognize(marker.points, gray)
                if rst:
                    marker.marker_id, marker.rotations = rst
                    markers.append(marker)
        else:
            markers = _markers

        if en_debug:
            return markers, thresh
        return markers