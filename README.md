# Room & Event Approval System

A database-driven web application for managing college committees, events, venues, booking requests, and approval workflows.

The system provides a centralized platform where committees can manage events, request venues, and track the approval status of bookings.

---

## Features

### Dashboard
- Total committees count
- Total venues count
- Total events count
- Pending booking requests count
- Approved requests count
- Recent booking requests activity table
- Venue capacity and campus space summary
- Quick operational action shortcuts

### Committee Management
- View committees directory
- Add new committee (Name, Faculty Advisor, Contact Email)
- Edit committee details
- Delete committee with confirmation dialog
- Search committees by name, advisor, or email
- Display linked events count per committee

### Venue Management
- View campus venues (Auditoriums, Seminar Halls, Labs, Meeting Rooms)
- Add new venue (Venue Name, Type, Location, Seating Capacity)
- Edit venue details
- Delete venue with confirmation dialog
- Search venues and filter by venue type
- Display capacity pills and location descriptions

### Event Management
- View registered college events and programs
- Create new event (Event Name, Date, Expected Attendees, Organizing Committee)
- Dynamic committee selection from registered committees
- Edit event details
- Delete event with confirmation dialog
- Search events and filter by organizing committee
- Quick "Book" shortcut button to initiate venue reservations for an event

### Booking Management
- Submit venue booking requests with event, venue, start time, and end time
- Dynamic event and venue selection
- Native datetime-local pickers with validation (end time must be after start time)
- Automatic initial status assignment (`Pending`)
- Update existing booking requests
- Delete booking request with confirmation dialog
- Clear status badges (**Pending**, **Approved**, **Rejected**)
- Filter bookings by status and venue, plus full-text search

### Approval Management
- Dedicated pending requests panel highlighting requests needing decision
- Direct capacity vs. expected attendees comparison to guide approvals
- Approve or reject booking requests with optional remarks
- Record approval decisions with timestamps and evaluator remarks
- Complete approval history and audit trail table
- Automatic synchronization of booking request statuses via MySQL trigger
- Search and filter approval history records by decision

---

## Technology Stack

### Frontend
- **HTML5**: Semantic layout, accessible modal dialogs, and forms
- **CSS3**: Modern dashboard design system, responsive flexbox/grid layout, custom status badges
- **JavaScript (Vanilla ES6+)**: Dynamic DOM manipulation, state management, modal controllers
- **Fetch API**: Asynchronous client-server communication with JSON payloads

### Backend
- **Python**: Core backend programming language
- **Flask**: Lightweight RESTful API framework with modular Blueprints
- **Flask-CORS**: Cross-Origin Resource Sharing support for frontend communication
- **MySQL Connector/Python**: Database driver for executing queries and transactions

### Database
- **MySQL**: Relational database management system (`event_area_approval`)
- **Triggers**: Automated workflow updates (booking status sync, booking time validation, overlap prevention)

---

## Project Structure

```text
Room_Event_Approval_System/
│
├── backend/
│   ├── routes/
│   │   ├── committee_routes.py
│   │   ├── venue_routes.py
│   │   ├── event_routes.py
│   │   ├── booking_routes.py
│   │   └── approval_routes.py
│   │
│   ├── app.py
│   ├── db.py
│   └── requirements.txt
│
├── frontend/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── app.js
│   ├── index.html
│   ├── committees.html
│   ├── venues.html
│   ├── events.html
│   ├── bookings.html
│   └── approvals.html
│
└── README.md
```

---

## Database Design

The relational database (`event_area_approval`) contains 5 core tables and automated triggers:

### Tables & Schema

1. **`committee`**
   - `committee_id` (INT, Primary Key, Auto Increment)
   - `name` (VARCHAR)
   - `advisor` (VARCHAR)
   - `contact_email` (VARCHAR)

2. **`venue`**
   - `venue_id` (INT, Primary Key, Auto Increment)
   - `venue_name` (VARCHAR)
   - `venue_type` (VARCHAR)
   - `location` (VARCHAR)
   - `capacity` (INT)

3. **`event`**
   - `event_id` (INT, Primary Key, Auto Increment)
   - `event_name` (VARCHAR)
   - `event_date` (DATE)
   - `expected_attendees` (INT)
   - `committee_id` (INT, Foreign Key referencing `committee.committee_id`)

4. **`booking_request`**
   - `request_id` (INT, Primary Key, Auto Increment)
   - `event_id` (INT, Foreign Key referencing `event.event_id`)
   - `venue_id` (INT, Foreign Key referencing `venue.venue_id`)
   - `start_time` (DATETIME)
   - `end_time` (DATETIME)
   - `created_at` (DATETIME / TIMESTAMP)
   - `status` (VARCHAR: `'Pending'`, `'Approved'`, `'Rejected'`)

5. **`approval`**
   - `approval_id` (INT, Primary Key, Auto Increment)
   - `request_id` (INT, Foreign Key referencing `booking_request.request_id`)
   - `decision` (VARCHAR: `'Approved'`, `'Rejected'`, `'Pending'`)
   - `remarks` (TEXT / VARCHAR)
   - `decided_at` (DATETIME / TIMESTAMP)

### Automated Triggers
- **`update_booking_status`**: Executes after inserting a record into `approval`. When a decision is marked `'Approved'` or `'Rejected'`, it automatically updates the matching `booking_request.status`.
- **`before_booking_insert`**: Ensures that any new booking request with an unspecified status defaults to `'Pending'`.
- **`validate_booking_time`**: Prevents booking requests where `end_time` is earlier than or equal to `start_time`.
- **`prevent_booking_overlap`**: Prevents concurrent overlapping bookings for the same venue where status is `'Pending'` or `'Approved'`.

---

## API Endpoints

Base API URL: `http://127.0.0.1:5000`

### System Health
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | API status and health check message |

### Committees (`/committees`)
| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| `GET` | `/committees` | Retrieve all committees | None |
| `GET` | `/committees/<id>` | Retrieve a single committee by ID | None |
| `POST` | `/committees` | Create a new committee | `{ "name", "advisor", "contact_email" }` |
| `PUT` | `/committees/<id>` | Update an existing committee | `{ "name", "advisor", "contact_email" }` |
| `DELETE` | `/committees/<id>` | Delete a committee by ID | None |

### Venues (`/venues`)
| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| `GET` | `/venues` | Retrieve all campus venues | None |
| `GET` | `/venues/<id>` | Retrieve a single venue by ID | None |
| `POST` | `/venues` | Create a new venue | `{ "venue_name", "venue_type", "location", "capacity" }` |
| `PUT` | `/venues/<id>` | Update an existing venue | `{ "venue_name", "venue_type", "location", "capacity" }` |
| `DELETE` | `/venues/<id>` | Delete a venue by ID | None |

### Events (`/events`)
| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| `GET` | `/events` | Retrieve all scheduled events | None |
| `GET` | `/events/<id>` | Retrieve a single event by ID | None |
| `POST` | `/events` | Create a new event | `{ "event_name", "event_date", "expected_attendees", "committee_id" }` |
| `PUT` | `/events/<id>` | Update an existing event | `{ "event_name", "event_date", "expected_attendees", "committee_id" }` |
| `DELETE` | `/events/<id>` | Delete an event by ID | None |

### Booking Requests (`/bookings`)
| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| `GET` | `/bookings` | Retrieve all booking requests | None |
| `GET` | `/bookings/<id>` | Retrieve a single booking request by ID | None |
| `POST` | `/bookings` | Create a new booking request | `{ "event_id", "venue_id", "start_time", "end_time" }` |
| `PUT` | `/bookings/<id>` | Update a booking request | `{ "event_id", "venue_id", "start_time", "end_time", "status" }` |
| `DELETE` | `/bookings/<id>` | Delete a booking request by ID | None |

### Approvals (`/approvals`)
| Method | Endpoint | Description | Request Body |
|---|---|---|---|
| `GET` | `/approvals` | Retrieve all approval history records | None |
| `GET` | `/approvals/<id>` | Retrieve a single approval record by ID | None |
| `POST` | `/approvals` | Record an approval or rejection | `{ "request_id", "decision", "remarks" }` |
| `PUT` | `/approvals/<id>` | Update an approval record | `{ "request_id", "decision", "remarks" }` |
| `DELETE` | `/approvals/<id>` | Delete an approval record by ID | None |

---

## Setup / Installation

### Prerequisites
- Python 3.9+ installed
- MySQL Server installed and running
- Modern web browser (Chrome, Edge, Firefox, Safari)

### 1. Database Setup
Ensure MySQL is running and import/configure the database credentials in `backend/db.py`:
```python
def get_db_connection():
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="YOUR_MYSQL_PASSWORD",
        database="event_area_approval"
    )
    return connection
```

### 2. Backend Installation
1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   - **Windows:**
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
3. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## How to Run

### 1. Start the Flask Backend Server
From the `backend/` directory (with virtual environment active):
```bash
python app.py
```
The Flask API will start at `http://127.0.0.1:5000`.

### 2. Launch the Frontend Dashboard
Open `frontend/index.html` in your web browser, or use a local HTTP server:
- Option A: Double-click `frontend/index.html` to open directly in your web browser.
- Option B: Use VS Code extension **Live Server** on `frontend/index.html`.
- Option C: Run a lightweight HTTP server:
  ```bash
  cd frontend
  python -m http.server 8000
  ```
  Then navigate to `http://127.0.0.1:8000` in your browser.

The frontend dashboard will automatically connect to `http://127.0.0.1:5000` and display a green "API Connected" indicator.

---

## Application Workflow

1. **Register Committees**:
   College committees (e.g., Technical, Cultural, Sports) are added with faculty advisor details and contact emails.
2. **Add Campus Venues**:
   Campus venues (e.g., Auditorium, Seminar Hall, Lab) are defined with seating capacity and building locations.
3. **Plan Events**:
   Events are created under specific committees with scheduled dates and expected attendee counts.
4. **Submit Booking Requests**:
   A committee representative selects an event, a venue, and the requested start and end times. The request is created with an initial status of `Pending`.
5. **Review & Approval**:
   Administrators open the Approvals section, review the requested venue and expected attendees, and submit their decision (`Approved` or `Rejected`) with remarks.
6. **Trigger-Driven Status Sync**:
   The MySQL trigger automatically updates the booking request status to match the approval decision, keeping all views and metrics synchronized in real time.

---

## Testing

### API Verification
You can test the backend endpoints directly using cURL or Postman:
```bash
# Check API health
curl http://127.0.0.1:5000/

# Fetch committees
curl http://127.0.0.1:5000/committees

# Fetch venues
curl http://127.0.0.1:5000/venues

# Fetch events
curl http://127.0.0.1:5000/events

# Fetch bookings
curl http://127.0.0.1:5000/bookings

# Fetch approvals
curl http://127.0.0.1:5000/approvals
```

### Frontend UI Verification
- Verify that dashboard metric cards update dynamically as records are added or modified.
- Verify that committee, venue, and event selection dropdowns populate automatically in the modal forms.
- Test client-side validations (e.g., ensuring booking end time is strictly after start time).
- Verify that approval decisions update the booking status badge and log entry in the audit trail.

---

## Future Enhancements

- **Role-Based Authentication**: Secure login roles for Student Committees, Faculty Advisors, and Venue Administrators.
- **Automated Email Notifications**: Automatic notification dispatch to advisors and coordinators upon booking status changes.
- **Interactive Calendar View**: Visual schedule grid to inspect venue availability across days and weeks.
- **Report Export**: Exporting booking histories and venue utilization metrics to PDF or Excel formats.