# 📦 User Manual: Inventory Control System

This user manual provides step-by-step instructions for warehouse operators and system administrators on how to interact with the web user interface at `http://localhost:8000/`.

---

## System Config Center

Before executing warehouse operations, administrators must configure the fundamental infrastructure of the warehouse via the **Config Center** located in the sidebar. 

**`Fleet & Operator Priorities`**
Before performing any actions, you must select your profile to establish your operator ID and priority.
1. click **+ ADD Profile**
2. can rename **NEW_USER_868** to any that you want then select **priority level** and then in **Assigned Role Description** you can rename Standard Operator to other that you want 
3. **Remove** botton can remove role that you want
   
> [!NOTE]
> Your profile priority determines queue placement:
> * **Priority 1 (High)**: Can immediately preempt (override) existing reservations made by Priority 2 users.
> * **Priority 2 (Standard)**: Placed in the queue if a slot is already reserved or occupied.

![priority](/static/operation_priority.png)

**`Storage Types Configuration`**
Define the physical storage formats (e.g., `rack`, `shelf`, `pallet`, `stacker`) and their extraction behaviors.
1. Click **+ Add Storage Type**.
2. **Storage Type Name**: Enter the physical name of the storage container.
3. **Picking Strategy**: 
   * **FIFO**: First-In, First-Out (Oldest items are retrieved first).
   * **LIFO**: Last-In, First-Out (Newest items are retrieved first).
4. **Action**: Click `Remove` to delete a storage type.

![unit](/static/unit_type_config.png)

**Item Types Configuration**
Define the standard goods you plan to store (e.g., `cookie`, `bunny`) to automatically populate operator dropdown menus.
1. Click **+ Add Item Type**.
2. Rename the newly added item to your desired good name.
3. Click the `Remove` button if you wish to delete an item type.

![item](/static/item_config.png)

**Storage Points Infrastructure**
Create and map physical node locations (e.g., `Shelf_A`), assign them a Storage Type, and specify the number of storage levels/shelves and their capacities.
1. Enter the point name in the text field and click **+ Add Node**.
2. Select the designated **Storage Type** for this storage point.
3. Expand **Show Levels Config** to set the max capacity and the specific allowed items for each level.
4. Each level can be uniquely renamed (e.g., `Level 1`, `Bottom Shelf`).

![storage](/static/storage_config.png)

**Sensor Mode Setup**
Choose between **Auto Mode** (where physical hardware sensors confirm slot statuses) or **Manual Mode** (where software UI buttons drive the state confirmations).

![select_mode](/static/select_mode.png)

---

## Depositing Inventory (Drop Operations)

To deposit an item into the warehouse, follow these steps to find a suitable slot and reserve it:
Navigate to the **Drop Operations** panel on the left.

![drop](/static/drop.png)

1. In the **Item Type** field, type the type of item you want to drop (e.g., `pallet`, `box`, `cookie`).
2. Click the red **FIND STORAGE** button.
3. A horizontal **Suggested Locations** carousel will appear:
   * **`MATCH`** (Green badge): Slot specifically designated for this item type. (Recommended)
   * **`ANY`** (Amber badge): Universal/wildcard slot that accepts any item type.
4. Click on any suggested slot card in the carousel. The slot's name will automatically populate the **Point Name** field.
5. if you have note at item you want to drop can add in **Operation Note**
6. finish select clik reauest drop botton 
    * auto mode is complete with sensor find item
    ![drop_item](/static/manual_drop.png)
    * manual mode is complete with click confirm botton
    ![drop_item](/static/auto_drop.png)


### Execute the Drop Reservation
1. **Add Notes (Optional)**: If you have additional information (e.g., "Fragile cargo", "Expire 2027"), you can type it directly into the **Operation Note** field before requesting.
2. Click the blue **CONFIRM DROP** button to secure your reservation.
3. Review the popup message:
   * **RESERVED**: You secured the slot! Proceed to the physical location.
   * **QUEUED**: The slot is busy. You are in the queue and must wait.
   * **PREEMPTED**: You overrode a lower-priority operator's reservation.

### Completing or Canceling the Task
After the slot is reserved (status changes to 🟨 `DROP_RESERVED`), you must finalize the process:
* **In Auto Mode (Sensors On)**: Physically place the item on the shelf. The system will automatically detect the object via the sensor and complete the task (status changes to `FULL`).
* **In Manual Mode (Sensors Off)**: Once you physically place the item, you must click the green **CONFIRM** button in the UI panel to finish the task.
* **Canceling the Task**: If you made a mistake or need to abort the operation before completion, click the red **CANCEL** button at any time to release your reservation.

---

## 📤 Retrieving Inventory (Pickup Operations)

To retrieve items from the warehouse, the system uses a configurable dispatch strategy (**FIFO** or **LIFO**) to determine which item to dispatch first (default is FIFO - First-In, First-Out).

### 1. Request a Pickup
1. Navigate to the **Pickup Operations** panel on the right.

![pick](/static/picckup_operation.png)

2. Enter the **Target Item Type** you wish to retrieve.
3. Click the teal **REQUEST PICKUP** button.
4. If the item is in stock, a **Target Dispatch Point** card will appear:
   * **Target Dispatch Point**: The slot name (e.g., `P-01`) from which you should retrieve the item.
   * **Payload Note**: Read any notes associated with this item to aid in retrieval.

![pick_item](/static/pickup_select.png)

### 2. Completing or Canceling the Task
After the system assigns a slot (status changes to 🟦 `PICKUP_RESERVED`), you must retrieve the item:
* **In Auto Mode (Sensors On)**: Proceed to the physical slot and remove the item. The system will detect the removal via the sensor and complete the task (status changes to `EMPTY`).
* **In Manual Mode (Sensors Off)**: Once you physically retrieve the item, you must click the green **CONFIRM** button in the UI panel to finish the task.
* **Canceling the Task**: If you decide not to pick up the item, click the red **CANCEL** button at any time to abort the operation and leave the item in the slot.

---

## 📊 Reading the Storage Grid Telemetry

The **Storage Slot Inventory** table at the bottom of the Dashboard provides a live view of the warehouse state:

*   **Allowed Categories**: Slots are grouped by allowed items. Each category group has a distinct pastel row background and left border color to help you quickly identify sections (e.g., box slots vs. pallet slots).
*   **Status Color Coding**:
    *   🟩 **`EMPTY`** (Teal): Vacant. Ready for drop requests.
    *   🟨 **`DROP_RESERVED`** (Pulsing Amber): Reserved. Waiting for item placement.
    *   🟥 **`FULL`** (Rose): Occupied. Contains inventory.
    *   🟦 **`PICKUP_RESERVED`** (Pulsing Indigo): In retrieval. Waiting for item removal.

*   **Disabled Slots**: Greyed-out rows represent inactive slots. Operators cannot reserve or interact with these slots.
*   **Hold States & Queues**:
    *   **Hold State**: Displays who is currently holding a reservation (e.g., `Hold: ROBOT_01`).
    *   **Queue**: Shows all operators waiting for the slot (e.g., `operator`, `human`) sorted by priority and request time.

---

## 🗺️ Interacting with the Isometric Map

The **Isometric Map** (located above the Inventory Flow table) provides a 2.5D visual representation of your storage floor plan.

*   **Zooming & Navigating**: Use the `+`, `-`, and `Reset` buttons in the map's header to adjust the scale, or simply scroll your mouse wheel while hovering over the map.
*   **Viewing Rack Details**: Click on any 3D storage node. The panel on the right (**Rack Details**) will display the full breakdown of every level within that rack, including what item is stored and its current status. Note that labels are intentionally hidden from the 3D map view to keep the interface clean; you must click a node to see its details.
*   **Editing the Layout**: 
    1. Toggle the **Edit Layout** button.
    2. Click an existing rack node to pick it up (it will turn green).
    3. Click any empty grid space to place the rack down in its new position.
    4. Click **Save Layout** to lock the arrangement and sync it to the backend.

---

## ⚠️ Handling Manual Mode Overrides (If Sensors are Disabled)

If your warehouse is running in **Manual Mode** (the Hardware Sensor header badge displays `Manual Mode`):

1. **Completing a Drop**: Once you place the item into a `DROP_RESERVED` slot, find the slot row in the Storage Grid and click the blue **Confirm** button. The system will verify the transaction log and transition the status to `FULL`.
2. **Completing a Pickup**: Once you retrieve the item from a `PICKUP_RESERVED` slot, click the blue **Confirm** button in that slot's row. The status will transition to `EMPTY` (or transition to `DROP_RESERVED` if there is a pending drop queue).
3. **Canceling Operations**: To safely abort a pending drop or pickup without completing it, click the red **Cancel** button. This clears the pending operation and automatically advances the queue if there are users waiting.
4. **Emergency Reset**: If a slot's software state gets stuck, you can click the white **Reset** button. This will clear all queued users and pending items. In **Manual Mode**, you will be prompted to select the new status (EMPTY or FULL) manually. In **Auto Mode**, the status will automatically sync to match whatever the physical hardware sensor reads.
5. **Manual Status Override**: You can forcefully change a slot's physical state using the status dropdown selector located directly in the slot's row.

> [!IMPORTANT]
> **Queue Promotion in Manual Mode**:
> When a pickup is confirmed on a slot that has pending users in its queue, the system automatically promotes the next user and shifts the slot status to `DROP_RESERVED`. Because sensors are disabled, you **must click Confirm again** on this slot once the promoted user's item is physically placed, in order to complete the drop and transition the slot status to `FULL`.

---

## 🛠️ Managing System Configurations (Administrators Only)

Click **Config Center** in the sidebar to access system configuration tools.

![config](/static/config_center.png)

### 1. Fleet & Operator Profiles (Priority Settings)
Before setting up the warehouse, you must configure the operators (or robots).
*   **Priority Level**: This is the most crucial setting. It determines who has the authority to bypass or preempt another operator's queue. An operator with Priority 1 can jump ahead of a Priority 2 operator who is already waiting for a slot.
*   **Add/Remove Operator**: Click **+ Add Profile**, edit the generated ID, select their priority level, and define their role (e.g., VIP Lifter, Human).

### 2. Storage Types Configuration
Next, define the physical infrastructure types used in your warehouse.
*   **Storage Type Name**: Name your storage type based on the physical storage container (e.g., `rack`, `shelf`, `pallet`, `stacker`).
*   **Picking Strategy**: Select whether this specific storage type operates on **FIFO** (First-In-First-Out) or **LIFO** (Last-In-First-Out). This dictates how the system queues multiple items stored within the same physical node.

### 3. Item Types Configuration
Define the specific goods or items that will be stored (e.g., `cookie`, `toy`). Adding items here populates dropdown lists for operators, though custom manual typing is still permitted in the dashboard.

### 4. Storage Points Infrastructure
*   **Add Node Name**: Enter the identifier (e.g., `P-10`) and click **+ Add Node**.
*   **Storage Type**: Assign one of the Storage Types (e.g., `rack`) you created earlier to this storage node.
*   **Hardware Mode**: Set to `Enabled` or `Disabled` for the specific point.
*   **Levels Config**: Click *Show Levels Config* to specify how many levels/shelves this node has, its max item capacity, and exactly what allowed item types it can accept.

### 5. Toggling Global Sensor Modes
*   Change the global **Enable Hardware Sensors** dropdown:
    *   **Enabled (Auto Mode)**: Automatically transitions states via physical sensors.
    *   **Disabled (Manual Mode)**: Suspends sensors; requires clicking the **Confirm** button in the dashboard or using dropdowns to override physical states.

> [!IMPORTANT]
> **CRITICAL STEP**: After making any changes in the Config Center, you must click the large green **SAVE ALL CONFIGURATIONS** button at the bottom of the page to apply them to `config.json` and sync the database.

---

## 📝 Auditing Warehouse Activity

Click **Activity Log** in the sidebar to view a transaction history of the warehouse.

![log](/static/log.png)

*   **Filter by User**: Type an operator ID to see only their drops and pickups.
*   **Filter by Slot**: Type a slot name (e.g., `P-01`) to track that specific location.
*   **Filter by Event**: Toggle between `ALL EVENTS`, `DROP EVENTS`, or `PICKUP EVENTS`.

---

## 📡 Headless Operation (API Integration)

The Inventory Control System is designed as an **API-First (Headless)** platform. The web UI is simply a client that consumes these APIs. This means you can entirely bypass the UI and integrate the system directly with external ERPs, PLCs, or robotic fleets using standard HTTP POST/GET requests.

### 1. Operations API
Control the flow of items programmatically:

*   **`POST /slot/drop`**: Reserve a slot. Automatically handles queuing and priority preemption.
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/slot/drop \
             -H "Content-Type: application/json" \
             -d '{"point_name": "P-01", "item_type": "cookie", "user_id": "ROBOT_01", "note": "express delivery"}'
        ```
    *   *Example Response*:
        ```json
        {
          "status": "RESERVED",
          "message": "Reserved P-01 for drop"
        }
        ```

*   **`POST /item/pickup`**: Request an item. Automatically finds the correct slot based on the FIFO/LIFO strategy.
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/item/pickup \
             -H "Content-Type: application/json" \
             -d '{"item_type": "cookie", "user_id": "ROBOT_01"}'
        ```
    *   *Example Response*:
        ```json
        {
          "status": "PICKUP_RESERVED",
          "target_slot": "P-01",
          "dispatched_item": {
            "item_type": "cookie",
            "in_time": "2026-07-07T10:38:14.501531",
            "note": "express delivery"
          }
        }
        ```

*   **`POST /slot/confirm`**: Manually confirm a transaction (when sensors are disabled).
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/slot/confirm \
             -H "Content-Type: application/json" \
             -d '{"point_name": "P-01"}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Confirmed P-01 Successful"
        }
        ```

*   **`POST /slot/cancel`**: Cancel a pending reservation.
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/slot/cancel \
             -H "Content-Type: application/json" \
             -d '{"point_name": "P-01"}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Cancelled operation at P-01"
        }
        ```

### 2. Sensor & Hardware API
Integrate with PLCs or IoT devices:

*   **`POST /sensor/state`**: Tell the system that a physical sensor has detected an item (True) or is empty (False).
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/sensor/state \
             -H "Content-Type: application/json" \
             -d '{"sensor_id": "S1", "detected": true}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Sensor state updated"
        }
        ```

*   **`GET /sensor/status`**: Poll current sensor states.
    *   *Example Command*:
        ```bash
        curl http://localhost:8000/sensor/status
        ```
    *   *Example Response*:
        ```json
        {
          "S1": true,
          "S2": false
        }
        ```

### 3. Configuration API
Configure the entire warehouse without opening the browser:

*   **`POST /config/mode`**: Toggle between Auto Mode (Sensors Enabled) and Manual Mode.
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/config/mode \
             -H "Content-Type: application/json" \
             -d '{"use_sensor": false}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Mode updated to Manual"
        }
        ```

*   **`POST /config/update`**: Overwrite all global configurations (Slots, Modes, Storage Types).
    *   *Payload Details*:
        *   `storage_types`: Defines the physical storage types (e.g. `rack`, `pallet`) and their `strategy` (`FIFO` or `LIFO`).
        *   `users`: Sets the operator array (with `priority` values 1 being highest).
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/config/update \
             -H "Content-Type: application/json" \
             -d '{"use_sensor": true, "slots": [], "users": [], "item_types": [], "storage_types": [{"name": "rack", "strategy": "FIFO"}], "map_layout": {}, "map_size": {"width": 10, "height": 10}}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Configuration successfully synchronized"
        }
        ```

*   **`POST /config/update/users`**: Update or merge the user/robot fleet priorities.
    *   *Payload Details*:
        *   `priority`: Defines who can bypass the queue (e.g., `1` is high priority / preempt-capable, `2` is standard).
        *   `role`: Describes the operator's authority or type (e.g., `VIP Lifter`).
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/config/update/users \
             -H "Content-Type: application/json" \
             -d '{"users": [{"user_id": "ROBOT_02", "priority": 1, "role": "LIFTER"}]}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "User configuration updated"
        }
        ```

*   **`POST /config/map`**: Update the 3D isometric map layout grid and grid size.
    *   *Example Command*:
        ```bash
        curl -X POST http://localhost:8000/config/map \
             -H "Content-Type: application/json" \
             -d '{"map_layout": {"P-01": {"x": 2, "y": 3}}, "map_size": {"width": 10, "height": 10}}'
        ```
    *   *Example Response*:
        ```json
        {
          "message": "Map layout updated"
        }
        ```

### 4. Data API

*   **`GET /slots`**: Retrieve the full Real-time JSON state of all storage slots, items, and queues.
    *   *Example Command*:
        ```bash
        curl http://localhost:8000/slots
        ```
    *   *Example Response*:
        ```json
        {
          "slots": [
            {
              "point_name": "P-01",
              "status": "EMPTY",
              "items": [],
              "queue": []
            }
          ],
          "users": [],
          "version": 5
        }
        ```

*   **`GET /history`**: Export the transaction audit logs.
    *   *Example Command*:
        ```bash
        curl "http://localhost:8000/history?limit=50"
        ```
    *   *Example Response*:
        ```json
        {
          "history": [
            {
              "time": "2026-09-17T10:45:00.000",
              "action": "DROP_CONFIRMED",
              "user_id": "ROBOT_01",
              "point_name": "P-01",
              "item_type": "cookie"
            }
          ]
        }
        ```

> For exact schemas and complete endpoint documentation, please refer to the developer `README.md` file in the project root.
