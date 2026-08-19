# User Manual: How to Use Inventory Control System

This user manual provides step-by-step instructions for warehouse operators and system administrators on how to interact with the web user interface at `http://localhost:8000/`.

---

## Set Up Your Profile (Operator Selection)

Before performing any actions, you must select your profile to establish your operator ID and priority.

1. Locate the **Operator Profile** card in the top-right corner of the Dashboard.
2. Click the dropdown menu showing the active profile (e.g., `ROBOT_01 (Priority 1)`).
3. Select your assigned ID from the list.
   
> [!NOTE]
> Your profile priority determines queue placement:
> * **Priority 1 (High)**: Can immediately preempt (override) existing reservations made by Priority 2 users.
> * **Priority 2 (Standard)**: Placed in the queue if a slot is already reserved or occupied.

![select](/static/select_user.png)

---

## Depositing Inventory (Drop Operations)

To deposit an item into the warehouse, follow these steps to find a suitable slot and reserve it:

### 1. Find an Eligible Storage
1. Navigate to the **Drop Operations** panel on the left.

![drop](/static/drop.png)

2. In the **Item Type** field, type the type of item you want to drop (e.g., `pallet`, `box`, `cookie`).
3. Click the red **FIND SLOTS** button.
4. A horizontal **Suggested Locations** carousel will appear:
   * **`MATCH`** (Green badge): Slot specifically designated for this item type. (Recommended)
   * **`ANY`** (Amber badge): Universal/wildcard slot that accepts any item type.

![drop_item](/static/drop_item.png)

5. Click on any suggested slot card in the carousel. The slot's name will automatically populate the **Point Name** field.

### 2. Confirm the Drop Reservation
1. (Optional) Enter any notes in the **Operation Note** field (e.g., "Fragile cargo", "Shelf 3").
2. Click the blue **CONFIRM DROP** button.
3. Review the popup Toast message in the center of the screen:
   * **RESERVED**: You secured the slot! Proceed to place the item in the physical slot.
   * **QUEUED**: The slot is busy. You have been placed in the queue; the system will reserve it for you once it becomes empty.
   * **PREEMPTED**: You overrode a lower-priority operator's reservation. The slot is now reserved for you.

---

## Retrieving Inventory (Pickup Operations)

To retrieve items from the warehouse, the system uses a strict **FIFO (First-In, First-Out)** order to dispatch the oldest item first.

1. Navigate to the **Pickup Operations** panel on the right.

![pick](/static/pick.png)

2. Enter the **Target Item Type** you wish to retrieve.
3. Click the teal **REQUEST PICKUP** button.
4. If the item is in stock, a **Target Dispatch Point** card will appear at the bottom of the panel:
   * **Target Dispatch Point**: The slot name (e.g., `P-01`) where the oldest item is located.
   * **Payload Note**: Read any notes associated with this item to aid in retrieval.

![pick_item](/static/pick_item.png)

5. Proceed to the indicated physical slot and retrieve the item.

---

## Reading the Storage Grid Telemetry

The **Storage Slot Inventory** table at the bottom of the Dashboard provides a live view of the warehouse state:

*   **Allowed Categories**: Slots are grouped by allowed items. Each category group has a distinct pastel row background and left border color to help you quickly identify sections (e.g., box slots vs. pallet slots).
*   **Status Color Coding**:
    *   🟩 **`EMPTY`** (Teal): Vacant. Ready for drop requests.
    *   🟨 **`DROP_RESERVED`** (Pulsing Amber): Reserved. Waiting for item placement.
    *   🟥 **`FULL`** (Rose): Occupied. Contains inventory.
    *   🟦 **`PICKUP_RESERVED`** (Pulsing Indigo): In retrieval. Waiting for item removal.

    ![status](/static/status.png)

*   **Disabled Slots**: Greyed-out rows represent inactive slots. Operators cannot reserve or interact with these slots.
*   **Hold States & Queues**:
    *   **Hold State**: Displays who is currently holding a reservation (e.g., `Hold: ROBOT_01`).
    *   **Queue**: Shows all operators waiting for the slot (e.g., `operator`, `human`) sorted by priority and request time.

    ![queue](/static/queue.png)

---

## Handling Manual Mode Overrides (If Sensors are Disabled)

If your warehouse is running in **Manual Mode** (the Hardware Sensor header badge displays `Manual Mode`):

![manual](/static/manual.png)

1. **Completing a Drop**: Once you place the item into a `DROP_RESERVED` slot, find the slot row in the Storage Grid and click the blue **Confirm** button. The system will verify the transaction log and transition the status to `FULL`.
2. **Completing a Pickup**: Once you retrieve the item from a `PICKUP_RESERVED` slot, click the blue **Confirm** button in that slot's row. The status will transition to `EMPTY` (or transition to `DROP_RESERVED` if there is a pending drop queue).
3. **Emergency Reset**: If a slot's state gets stuck or configuration changes require it, administrators can click the white **Reset** button on any slot row to instantly clear all items and queues.

> [!IMPORTANT]
> **Queue Promotion in Manual Mode**:
> When a pickup is confirmed on a slot that has pending users in its queue, the system automatically promotes the next user and shifts the slot status to `DROP_RESERVED`. Because sensors are disabled, you **must click Confirm again** on this slot once the promoted user's item is physically placed, in order to complete the drop and transition the slot status to `FULL`.

---

## Managing System Configurations (Administrators Only)

Click **Config Center** in the sidebar to access system configuration tools.

![config](/static/config.png)

### 1. Fleet & Operator Profiles
*   **Add Operator**: Click **+ Add Profile**, then edit the generated ID, select their priority level, and write their role.
*   **Remove Operator**: Click **Remove** next to any operator profile.

### 2. Physical Slot Setup
*   **Add Slot Node**: Enter a name in the text box (e.g., `P-07`) and click **+ Add Node**.
*   **Set Allowed Items**: In the **Allowed Items** input, type a comma-separated list of item types (e.g., `box,pallet`). Leave blank or enter `*` to allow any item.
*   **Toggle Slot State**: Change the **Hardware Mode** dropdown to `Enabled` or `Disabled`.
*   **Delete Slot Node**: Click **Delete** next to the slot node.

### 3. Toggling Sensor Modes
*   Change the **Enable Hardware Sensors** dropdown:
    *   **Enabled (Use sensor inputs)**: Automatically transitions states via physical sensors.
    *   **Disabled (Complete transactions manually)**: Suspends sensors; requires clicking the **Confirm** button in the dashboard grid.

> [!IMPORTANT]
> **CRITICAL STEP**: After making any changes in the Config Center, you must click the large green **SAVE ALL CONFIGURATIONS** button at the bottom of the page to apply them to `config.json` and sync the database.

---

## Auditing Warehouse Activity

Click **Activity Log** in the sidebar to view a transaction history of the warehouse.

![log](/static/log.png)

*   **Filter by User**: Type an operator ID to see only their drops and pickups.
*   **Filter by Slot**: Type a slot name (e.g., `P-01`) to track that specific location.
*   **Filter by Event**: Toggle between `ALL EVENTS`, `DROP EVENTS`, or `PICKUP EVENTS`.

---

## QR Code Scanning & Camera Operations

The Inventory Control System includes integrated optical QR barcode scanning:

### 1. Fast Scanning for Drop / Pickup
*   **Drop Operations**: Click the **Scan QR** button in the Drop Operations panel. Hold the item's barcode in front of the camera; the system will decode the payload and automatically trigger **FIND STORAGE**.
*   **Pickup Operations**: Click the **Scan QR** button in the Pickup Operations panel to quickly populate the target item type.

### 2. QR Code Formats Supported
*   **Plain Text**: e.g., `box`, `cookie`, `pallet` (auto-mapped to Item Type).
*   **JSON Payload**: Structured QR codes such as:
    ```json
    {
      "item_type": "box",
      "point_name": "P-02",
      "user_id": "ROBOT_01",
      "note": "Batch #104"
    }
    ```

### 3. QR Camera Live Monitor
*   Click **QR Camera Feed** in the dashboard header to open the live camera view.
*   Preview the real-time video feed at `/video_feed`.
*   Switch video input devices dynamically if multiple cameras are connected.
*   Perform **Auto-Adjust** to optimize luminance and contrast for difficult-to-read barcodes.

### 4. REST API Endpoints
*   `GET / POST /read`: Trigger QR barcode scan and return parsed data.
*   `GET /video_feed`: MJPEG live video stream.
*   `GET /cap_screen`: Retrieve last captured QR frame image or JSON metadata.
*   `GET /cameras` & `POST /cameras/switch`: Device discovery and switching.
*   `POST /slot/drop/scan`: Automated drop with direct QR camera scan.
*   `POST /item/pickup/scan`: Automated FIFO pickup with direct QR camera scan.

