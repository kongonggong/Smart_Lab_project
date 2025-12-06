import cv2

cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
if not cap.isOpened():
    print("Cannot open camera")
    exit()

while True:
    ok, frame = cap.read()
    if not ok:
        print("failed to read")
        break

    cv2.imshow("test camera", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
