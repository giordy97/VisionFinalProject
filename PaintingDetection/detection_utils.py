import numpy as np
import cv2
import math
import scipy.spatial.distance
import matplotlib.pyplot as plt

from rectification_utils import houghLines
from retrieval_utils import orb_features_matching

from pyimagesearch.transform import four_point_transform
from skimage.filters import threshold_local
import imutils


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


def print_rectangles_with_findContours(edged, frame):
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    rects = np.ones([len(contours), ])
    bounding_boxes = []
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
                        # cv2.imshow("First", cv2.rectangle(frame.copy(), (x0, y0), (x0 + w0, y0 + h0), (0, 255, 0), 2))
                        # cv2.waitKey()
                        # cv2.imshow("Second", cv2.rectangle(frame.copy(), (x1, y1), (x1 + w1, y1 + h1), (0, 255, 0), 2))
                        # cv2.waitKey()
                        if bb_intersection_over_union((x0, y0, w0, h0), (x1, y1, w1, h1)) > 0.6:
                            if w0*h0 > w1*h1:
                                rects[j] = 0
                            else:
                                rects[i] = 0
                        # cv2.destroyAllWindows()
            if rects[i] == 1:
                # ret = orb_features_matching(frame[y0:y0+h0, x0:x0+w0, :])
                # print(ret, '\n\n')
                # ret = kmeans(frame[y0:y0+h0, x0:x0+w0, :])
                # ret = watershed(frame[y0:y0+h0, x0:x0+w0, :])
                # (x0, y0, w0, h0) = second_step(frame[y0:y0 + h0, x0:x0 + w0, :])
                ret, bb = second_step(frame[
                                      max(0, y0-DELTA): min(frame.shape[0], y0+h0+DELTA),
                                      max(0, x0-DELTA): min(frame.shape[1], x0+w0+DELTA),
                                      :])
                # ret, bb = second_step(frame[y0:y0+h0, x0:x0+w0, :])
                if ret:
                    bounding_boxes.append(bb)
    return frame, bounding_boxes


def second_step(img):
    img = enlight(img)
    ratio = img.shape[0] / 500.0
    orig = img.copy()
    img = imutils.resize(img, height=500)
    black_img = np.zeros(img.shape, np.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    cv2.imshow('HSV', hsv)
    # cv2.imshow('RGB', img)
    rgb_gray = preprocessing(img)
    hsv_gray = preprocessing(hsv)
    # Otsu thresholding
    _, thresh1 = cv2.threshold(rgb_gray, 0, 255, cv2.THRESH_OTSU)
    _, thresh2 = cv2.threshold(hsv_gray, 0, 255, cv2.THRESH_OTSU)
    rgb_gray = (rgb_gray > thresh1).astype(np.uint8) * 255
    hsv_gray = (hsv_gray > thresh2).astype(np.uint8) * 255
    # cv2.imshow('RGB_otsu', rgb_gray)
    cv2.imshow('HSV_otsu_start', hsv_gray)

    cnts, _ = cv2.findContours(hsv_gray.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for contour in cnts:
        bb = cv2.boundingRect(contour)
        if bb == (0, 0, img.shape[1], img.shape[0]):
            hsv_gray = (hsv_gray < thresh2).astype(np.uint8) * 255
            break
    cv2.imshow('HSV_otsu_end', hsv_gray)
    cv2.waitKey()
    # find the contours in the edged image, keeping only the
    # largest ones, and initialize the screen contour
    cnts = cv2.findContours(hsv_gray.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = imutils.grab_contours(cnts)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

    # loop over the contours
    for c in cnts:
        if cv2.contourArea(c) < 45000:
            continue
        # approximate the contour
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        try:
            x, y, w, h = cv2.boundingRect(c)
            cv2.imshow('bb_cnt', img[y:y + h, x:x + w, :])
            canvas = black_img.copy()
            cv2.drawContours(canvas, [approx], -1, (255, 255, 255), 1)
            cv2.imshow("Outline before houghLines", canvas[:, :, 0])
            cv2.waitKey(0)
            if len(approx) == 4:
                screenCnt = approx
                break



            # ret = houghLines(canvas[:, :, 0])
            # cv2.imshow("Outline", ret)
            # cv2.waitKey(0)

            # contours = cv2.findContours(ret.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            # contours = imutils.grab_contours(contours)
            # contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]
            # for i, c1 in enumerate(contours):
            #     # approximate the contour
            #     peri1 = cv2.arcLength(c1, True)
            #     approx1 = cv2.approxPolyDP(c1, 0.02 * peri1, True)
            #     my_canvas = black_img.copy()
            #     cv2.drawContours(my_canvas, [approx], -1, (0, 255, 0), 1)
            #     cv2.imshow('c'+str(i), my_canvas)
            #     cv2.waitKey(0)
            #     # if our approximated contour has four points, then we
            #     # can assume that we have found our screen
            #     if len(approx1) == 4:
            #         screenCnt1 = approx1
            #         break
            # cv2.destroyAllWindows()
            # print("STEP 2: Find contours of paper")
            # cv2.drawContours(img, [screenCnt1], -1, (0, 255, 0), 2)
            # cv2.imshow("Outline", img)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()

            #
            #
            # print("Score: ", np.mean(hsv_gray[y:y+h, x:x+w]))
            # print("Mean hsv 2: ", np.mean(hsv[:, :, 2]))
            # print("Std hsv 2: ", np.std(hsv[:, :, 2]))
            # keypoints = np.zeros([4, 2])
            # keypoints[0] = [x, y]
            # keypoints[1] = [x + w, y]
            # keypoints[2] = [x, y + h]
            # keypoints[3] = [x + w, y + h]
            # # non va perchè i punti che dò in input non sono punti del quadro distorto ma un bb con già i lati paralleli
            # warped = four_point_transform(orig[y:y + h, x:x + w, :], keypoints * ratio)
            # # show the original and rectified images
            # print("STEP 3: Apply perspective transform")
            # cv2.imshow("Original", imutils.resize(orig, height=500))
            # cv2.imshow("Warped", imutils.resize(warped, height=500))
            # cv2.waitKey(0)
        except Exception as e:
            print(e)
        # if our approximated contour has four points, then we
        # can assume that we have found our screen
        # if len(approx) == 4:
        #     screenCnt = approx
        #     break
    try:
        # show the contour (outline) of the piece of paper
        print("STEP 2: Find contours of paper")
        cv2.drawContours(img, [screenCnt], -1, (0, 255, 0), 2)
        cv2.imshow("Outline", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        # apply the four point transform to obtain a top-down
        # view of the original image
        keypoints = screenCnt.reshape(4, 2)
        # keypoints = [[x,y], [x+w,y], [x,y+h], [x+w,y+h]]
        warped = four_point_transform(orig, keypoints * ratio)
        # show the original and rectified images
        print("STEP 3: Apply perspective transform")
        cv2.imshow("Original", imutils.resize(orig, height=500))
        cv2.imshow("Warped", imutils.resize(warped, height=500))
        cv2.waitKey(0)
    except:
        pass
    return True, (0, 0, 0, 0)


def enlight(rgb_img):
    cv2.imshow('Original', rgb_img)
    hsv = cv2.cvtColor(rgb_img, cv2.COLOR_BGR2HSV)
    hsv[:, :, 2] += LIGHT_FACTOR
    # final image has still problems even after clip, I don't know why
    hsv[:, :, 0] = np.clip(hsv[:, :, 0], 0, 179)
    hsv[:, :, 1:] = np.clip(hsv[:, :, 1:], 0, 255)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    cv2.imshow('Lighted', rgb)
    cv2.waitKey()
    return rgb


def kmeans(frame):
    image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # reshape the image to a 2D array of pixels and 3 color values (RGB)
    pixel_values = image.reshape((-1, 3))
    # convert to float
    pixel_values = np.float32(pixel_values)
    # define stopping criteria
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    # number of clusters (K)
    k = 3  # one for background and one for paintings (also one for paintings' frames?)
    _, labels, (centers) = cv2.kmeans(pixel_values, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    # convert back to 8 bit values
    centers = np.uint8(centers)
    # flatten the labels array
    labels = labels.flatten()
    # convert all pixels to the color of the centroids
    segmented_image = centers[labels.flatten()]
    # reshape back to the original image dimension
    segmented_image = segmented_image.reshape(image.shape)
    # show the image
    plt.imshow(segmented_image)
    plt.show()
    # # disable only the cluster number 1 (turn the pixel into black)
    # masked_image = np.copy(image)
    # # convert to the shape of a vector of pixel values
    # masked_image = masked_image.reshape((-1, 3))
    # # color (i.e cluster) to disable
    # cluster = 1
    # masked_image[labels == cluster] = [0, 0, 0]
    # # convert back to original shape
    # masked_image = masked_image.reshape(image.shape)
    # # show the image
    # plt.imshow(masked_image)
    # plt.show()
    return segmented_image


def watershed(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # noise removal
    kernel = np.ones((3, 3), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
    # sure background area
    sure_bg = cv2.dilate(opening, kernel, iterations=3)
    # plt.imshow(sure_bg, cmap='gray')
    # plt.show()
    # Finding sure foreground area
    dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
    ret, sure_fg = cv2.threshold(dist_transform, 0.7 * dist_transform.max(), 255, 0)
    # Finding unknown region
    sure_fg = np.uint8(sure_fg)
    # plt.imshow(sure_fg, cmap='gray')
    # plt.show()
    unknown = cv2.subtract(sure_bg, sure_fg)
    # Marker labelling
    ret, markers = cv2.connectedComponents(sure_fg)
    # Add one to all labels so that sure background is not 0, but 1
    markers = markers + 1
    # Now, mark the region of unknown with zero
    markers[unknown == 255] = 0
    markers = cv2.watershed(img, markers)
    img[markers == -1] = [255, 0, 0]
    cv2.imshow('watershed', img)
    cv2.waitKey()
    return img


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
    cv2.imshow('rgb_hsv', gray)
    # ret = kmeans(img)

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
    cv2.imshow('gray_hsv', gray)
    cv2.waitKey()
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
