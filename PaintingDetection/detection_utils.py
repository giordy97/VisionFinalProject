import numpy as np
import cv2
import imutils

from PaintingDetection.rectification_utils import houghLines
from PaintingDetection.retrieval_utils import orb_features_matching
from PaintingDetection.pyimagesearch.transform import four_point_transform

DELTA = 30
LIGHT_FACTOR = 40


def bb_intersection_over_union(boxA, boxB):
    # determine the (x, y)-coordinates of the intersection rectangle
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    # compute the area of intersection rectangle
    interArea = max(0, xB - xA) * max(0, yB - yA)
    # compute the area of the smaller rectangle
    boxArea = min(boxA[2] * boxA[3], boxB[2] * boxB[3])
    # compute the intersection over union
    iou = interArea / float(boxArea)
    return iou


def first_step(edged, frame, db_paintings):
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rects = np.ones([len(contours), ])
    bounding_boxes = []
    rectified_images = []
    # select only valid contours
    for i, contour in enumerate(contours):
        try:
            (x0, y0, w0, h0) = cv2.boundingRect(contour)
            if w0 * h0 < 50000:
                rects[i] = 0
        except:
            rects[i] = 0
    # display only rectangles not inside other rectangles
    for i, contour in enumerate(contours):
        if rects[i]:
            (x0, y0, w0, h0) = cv2.boundingRect(contour)
            for j, c in enumerate(contours):
                if rects[j]:
                    # check if the rectangles are different
                    if np.all(c == contour):
                        continue
                    else:
                        # check if c is inside contour
                        (x1, y1, w1, h1) = cv2.boundingRect(c)
                        if bb_intersection_over_union((x0, y0, w0, h0), (x1, y1, w1, h1)) > 0.6:
                            if w0*h0 > w1*h1:
                                rects[j] = 0
                            else:
                                rects[i] = 0
            if rects[i] == 1:
                # questa funzione passa a second step il frame com la bounding box sopra, questo va rovinare processo di
                # rettifica del quadro, era voluto?
                cv2.rectangle(frame, (x0, y0), (x0 + w0, y0 + h0), (0, 255, 0), 2)
                bounding_boxes.append((x0, y0, w0, h0))
                ret, warped = second_step(frame[
                                      max(0, y0-DELTA): min(frame.shape[0], y0+h0+DELTA),
                                      max(0, x0-DELTA): min(frame.shape[1], x0+w0+DELTA),
                                      :], db_paintings)
                if warped is not None:
                    rectified_images.append(warped)
    return frame, bounding_boxes, rectified_images


# second step not working well if the painting doesn't have a rectangular shape
def second_step(orig, db_paintings):
    ret = False
    orig = enlight(orig)
    ratio = orig.shape[0] / 500.0
    black_img = np.zeros(orig.shape)
    img = imutils.resize(orig, height=500)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # cv2.imshow('HSV', hsv)
    # cv2.imshow('RGB', orig)
    # cv2.waitKey()
    # rgb_gray image has the only purpose to visualize the differences between rgb and hsv
    # rgb_gray = preprocessing(img)
    hsv_gray = preprocessing(hsv)
    # Otsu thresholding
    # _, thresh1 = cv2.threshold(rgb_gray, 0, 255, cv2.THRESH_OTSU)
    _, thresh = cv2.threshold(hsv_gray, 0, 255, cv2.THRESH_OTSU)
    # rgb_gray = (rgb_gray > thresh1).astype(np.uint8) * 255
    hsv_gray = (hsv_gray > thresh).astype(np.uint8) * 255
    # cv2.imshow('RGB_otsu', rgb_gray)
    # cv2.imshow('HSV_otsu_start', hsv_gray)

    # sometimes the background has been filled with 255 and the painting with 0
    # the following code make sure that the background is filled with 0,
    # otherwise findCountours will not work well
    cnts, _ = cv2.findContours(hsv_gray.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for contour in cnts:
        bb = cv2.boundingRect(contour)
        if bb == (0, 0, img.shape[1], img.shape[0]):
            hsv_gray = (hsv_gray < thresh).astype(np.uint8) * 255
            break
    # cv2.imshow('HSV_otsu_end', hsv_gray)
    # cv2.waitKey()
    # find the contours in the edged image, keeping only the
    # largest ones, and initialize the screen contour
    cnts = cv2.findContours(hsv_gray.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:10]

    # loop over the contours
    for c in cnts:
        if cv2.contourArea(c) < 45000:
            continue
        # approximate the contour
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        x, y, w, h = cv2.boundingRect(c)
        # cv2.imshow('bb_cnt', img[y:y + h, x:x + w, :])
        # ToDo: call orb feature matching with img[y:y + h, x:x + w, :] as input
        # orb_features_matching(img[y:y + h, x:x + w, :], db_paintings)
        # uncomment the following lines if you want to visualize the contours
        # canvas = black_img.copy()
        # cv2.drawContours(canvas, [approx], -1, (255, 255, 255), 1)
        # cv2.imshow("Outline only", canvas[:, :, 0])
        # cv2.waitKey(0)
        # if our approximated contour has four points, then we
        # can assume that we have found our painting
        if len(approx) == 4:
            ret = True
            screenCnt = approx
            break
    try:
        # show the contour (outline) of the painting
        cv2.drawContours(img, [screenCnt], -1, (255, 0, 0), 15)
        # cv2.imshow("Outline", img)
        # cv2.waitKey(0)
        cv2.destroyAllWindows()
        # apply the four point transform to obtain a top-down view of the painting
        keypoints = screenCnt.reshape(4, 2)
        warped = four_point_transform(orig, keypoints * ratio)
        # show both original and rectified images
        # cv2.imshow("Original", imutils.resize(orig, height=500))
        # cv2.imshow("Warped", imutils.resize(warped, height=500))
        # cv2.waitKey(0)
    except:
        ret = False
    try:
        return ret, warped
    except:
        return ret, None


def enlight(rgb_img):
    # cv2.imshow('Original', rgb_img)
    rgb = rgb_img.astype(np.uint16)
    rgb[:, :, :] += LIGHT_FACTOR
    rgb = np.clip(rgb, 0, 255)
    rgb = rgb.astype(np.uint8)
    # cv2.imshow('Lighted', rgb)
    # cv2.waitKey()
    return rgb


def preprocessing(frame):
    # convert the image to grayscale, blur it, and find edges
    # in the image
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # apply bilateral filter
    gray = cv2.bilateralFilter(gray, 9, 40, 40)
    return gray


def method_0(frame):
    gray = preprocessing(frame)
    # Canny edge detection
    edged = cv2.Canny(gray, 25, 50)
    # cv2.imshow('Canny', edged)

    # dilate borders
    dilate_kernel = np.ones((5, 5), np.uint8)
    edged = cv2.dilate(edged, dilate_kernel, iterations=2)
    # cv2.imshow('Canny + dilate', edged)
    return edged


def method_1(frame):
    gray = preprocessing(frame)
    # Otsu thresholding
    _, thresh1 = cv2.threshold(gray, 120, 255, cv2.THRESH_OTSU)
    gray = (gray > thresh1).astype(np.uint8) * 255
    # cv2.imshow('rgb_hsv', gray)

    # dilate borders
    dilate_kernel = np.ones((5, 5), np.uint8)
    edged = cv2.dilate(gray, dilate_kernel, iterations=2)
    return edged


# very good in some situations but bad in others
# method 1 is more stable
def method_2(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = preprocessing(hsv)
    # Otsu thresholding
    _, thresh1 = cv2.threshold(gray, 120, 255, cv2.THRESH_OTSU)
    gray = (gray < thresh1).astype(np.uint8) * 255
    # cv2.imshow('gray_hsv', gray)
    # cv2.waitKey()
    # ret = kmeans(img)

    # dilate borders
    dilate_kernel = np.ones((5, 5), np.uint8)
    edged = cv2.dilate(gray, dilate_kernel, iterations=2)
    return edged


def isolate_painting(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_frame_color = np.array([15, 19, 24])
    upper_frame_color = np.array([110, 143, 171])
    mask = cv2.inRange(hsv, lower_frame_color, upper_frame_color)
    return mask
