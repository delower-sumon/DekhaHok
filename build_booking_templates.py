import re

def process_template(input_file, output_file, mode):
    with open(input_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 1. Remove the entire booking wizard steps container
    start_str = '<!-- Progress Bar -->'
    end_str = '<!-- Step 3: Success -->'
    
    start_idx = html.find(start_str)
    end_idx = html.find(end_str)
    
    if start_idx != -1 and end_idx != -1:
        # We want to replace everything between start_idx and end_idx
        if mode == 'session':
            replacement = """
    <!-- Session Booking Flow -->
    <div id="session-wizard" class="bg-white border border-emerald-100 rounded-3xl p-6 shadow-sm mb-8 relative overflow-hidden">
        <h2 class="text-xl font-bold text-zinc-900 mb-6">Book a 1-on-1 Session</h2>
        
        <div id="step-1-slots" class="space-y-4">
            <h3 class="text-sm font-bold text-emerald-800">1. Select an Available Slot</h3>
            <div id="slots-container" class="flex flex-wrap gap-3">
                <p class="text-zinc-500 text-sm">Loading slots...</p>
            </div>
        </div>

        <div id="step-2-details" class="space-y-4 mt-8 hidden">
            <h3 class="text-sm font-bold text-emerald-800 border-t pt-6">2. Your Details</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input type="text" id="session-name" placeholder="Full Name" class="border rounded-xl px-4 py-3 text-sm w-full" value="{{ user.name if user else '' }}">
                <input type="tel" id="session-phone" placeholder="Phone (01...)" class="border rounded-xl px-4 py-3 text-sm w-full">
                <input type="email" id="session-email" placeholder="Email" class="border rounded-xl px-4 py-3 text-sm w-full sm:col-span-2" value="{{ user.email if user else '' }}">
            </div>
            
            <h3 class="text-sm font-bold text-emerald-800 border-t pt-6 mt-4">3. Payment</h3>
            <div class="bg-emerald-50 rounded-xl p-4 border border-emerald-100 flex justify-between items-center">
                <span class="text-sm font-bold text-zinc-700">Total Fee</span>
                <span class="text-lg font-black text-emerald-700" id="session-fee-display">৳0</span>
            </div>
            
            <button onclick="submitSession()" id="btn-submit-session" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3.5 rounded-xl transition shadow mt-4">Confirm & Book</button>
        </div>
    </div>
"""
        else:
            replacement = """
    <!-- Hire Request Flow -->
    <div id="hire-wizard" class="bg-white border border-emerald-100 rounded-3xl p-6 shadow-sm mb-8 relative overflow-hidden">
        <h2 class="text-xl font-bold text-zinc-900 mb-6">Request to Hire Artist</h2>
        
        <div id="hire-form" class="space-y-4">
            <h3 class="text-sm font-bold text-emerald-800">1. Occasion Details</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input type="text" id="hire-occasion" placeholder="Occasion (e.g. Wedding, Birthday)" class="border rounded-xl px-4 py-3 text-sm w-full">
                <input type="date" id="hire-date" class="border rounded-xl px-4 py-3 text-sm w-full">
                <input type="text" id="hire-location" placeholder="Location/Venue" class="border rounded-xl px-4 py-3 text-sm w-full">
                <input type="number" id="hire-guests" placeholder="Expected Guest Count" class="border rounded-xl px-4 py-3 text-sm w-full">
                <select id="hire-budget" class="border rounded-xl px-4 py-3 text-sm w-full sm:col-span-2">
                    <option value="" disabled selected>Select Budget Range</option>
                    <option value="Under 1k">Under ৳1,000</option>
                    <option value="1k - 5k">৳1,000 - ৳5,000</option>
                    <option value="5k - 10k">৳5,000 - ৳10,000</option>
                    <option value="10k - 30k">৳10,000 - ৳30,000</option>
                    <option value="Above 30k">Above ৳30,000</option>
                </select>
                <textarea id="hire-message" placeholder="Message to Artist..." class="border rounded-xl px-4 py-3 text-sm w-full sm:col-span-2 h-24"></textarea>
            </div>
            
            <h3 class="text-sm font-bold text-emerald-800 border-t pt-6 mt-4">2. Your Details</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <input type="text" id="hire-name" placeholder="Full Name" class="border rounded-xl px-4 py-3 text-sm w-full" value="{{ user.name if user else '' }}">
                <input type="tel" id="hire-phone" placeholder="Phone (01...)" class="border rounded-xl px-4 py-3 text-sm w-full">
                <input type="email" id="hire-email" placeholder="Email" class="border rounded-xl px-4 py-3 text-sm w-full sm:col-span-2" value="{{ user.email if user else '' }}">
            </div>
            
            <button onclick="submitHire()" id="btn-submit-hire" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3.5 rounded-xl transition shadow mt-6">Send Request</button>
        </div>
    </div>
"""
        html = html[:start_idx] + replacement + "\n    " + html[end_idx:]

    # Now replace the JS functions at the bottom
    js_start = html.find('function selectPaymentMode')
    js_end = html.rfind('</script>')
    
    if js_start != -1 and js_end != -1:
        if mode == 'session':
            js_replacement = """
    let selectedSlotId = null;

    async function loadSlots() {
        const res = await fetch(`/api/events/${TARGET_EVENT_ID}/slots`);
        const data = await res.json();
        const container = document.getElementById('slots-container');
        
        if(data.slots.length === 0) {
            container.innerHTML = '<p class="text-rose-500 font-bold text-sm">No slots available.</p>';
            return;
        }
        
        container.innerHTML = data.slots.map(s => {
            if(s.is_booked) {
                return `<div class="px-4 py-3 border rounded-xl bg-zinc-50 text-zinc-400 text-sm line-through cursor-not-allowed">
                    ${new Date(s.slot_time).toLocaleString('en-US', {timeZone: 'Asia/Dhaka', weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit', hour12: true})}
                </div>`;
            }
            return `<button onclick="selectSlot(${s.id}, this)" class="slot-btn px-4 py-3 border border-emerald-200 rounded-xl text-emerald-800 text-sm font-bold hover:bg-emerald-50 transition text-left">
                ${new Date(s.slot_time).toLocaleString('en-US', {timeZone: 'Asia/Dhaka', weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit', hour12: true})}
            </button>`;
        }).join('');
    }

    function selectSlot(slotId, btnElement) {
        selectedSlotId = slotId;
        document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('bg-emerald-600', 'text-white'));
        document.querySelectorAll('.slot-btn').forEach(b => b.classList.add('text-emerald-800'));
        btnElement.classList.remove('bg-emerald-50', 'text-emerald-800');
        btnElement.classList.add('bg-emerald-600', 'text-white');
        
        document.getElementById('step-2-details').classList.remove('hidden');
        document.getElementById('session-fee-display').textContent = `৳${selectedEvent.price_per_person}`;
    }

    async function submitSession() {
        if(!selectedSlotId) return alert('Please select a slot');
        
        const payload = {
            slot_id: selectedSlotId,
            event_id: TARGET_EVENT_ID,
            name: document.getElementById('session-name').value,
            phone: document.getElementById('session-phone').value,
            email: document.getElementById('session-email').value
        };
        
        if(!payload.name || !payload.phone) return alert("Name and phone required");
        
        document.getElementById('btn-submit-session').disabled = true;
        document.getElementById('btn-submit-session').textContent = "Processing...";
        
        try {
            const res = await fetch('/api/sessions/book', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if(res.ok) {
                document.getElementById('session-wizard').classList.add('hidden');
                document.getElementById('booking-event-card').classList.add('hidden');
                document.getElementById('booking-media-container').classList.add('hidden');
                document.getElementById('booking-step-3').classList.remove('hidden');
                document.getElementById('success-ticket-id').textContent = data.tracking_id;
            } else {
                alert(data.detail || "Booking failed");
                document.getElementById('btn-submit-session').disabled = false;
                document.getElementById('btn-submit-session').textContent = "Confirm & Book";
            }
        } catch(e) {
            alert("Network error");
        }
    }

    // After initBookingPage logic runs, we load slots
    const originalInit = initBookingPage;
    initBookingPage = async function() {
        await originalInit();
        loadSlots();
    };
"""
        else:
            js_replacement = """
    async function submitHire() {
        const payload = {
            host_id: selectedEvent.host_id,
            event_id: TARGET_EVENT_ID,
            occasion_type: document.getElementById('hire-occasion').value,
            event_date: document.getElementById('hire-date').value || null,
            event_location: document.getElementById('hire-location').value,
            guest_count: parseInt(document.getElementById('hire-guests').value) || null,
            budget_range: document.getElementById('hire-budget').value,
            message: document.getElementById('hire-message').value,
            client_name: document.getElementById('hire-name').value,
            client_phone: document.getElementById('hire-phone').value,
            client_email: document.getElementById('hire-email').value
        };
        
        if(!payload.client_name || !payload.client_phone) return alert("Name and phone required");
        
        document.getElementById('btn-submit-hire').disabled = true;
        document.getElementById('btn-submit-hire').textContent = "Sending Request...";
        
        try {
            const res = await fetch('/api/hire', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if(res.ok) {
                document.getElementById('hire-wizard')?.classList.add('hidden');
                document.getElementById('booking-event-card')?.classList.add('hidden');
                document.getElementById('booking-media-container')?.classList.add('hidden');
                document.getElementById('booking-step-3')?.classList.remove('hidden');
                document.getElementById('success-ticket-id').textContent = data.tracking_id;
                const trackBtn = document.getElementById('btn-track-booking');
                if(trackBtn) trackBtn.href = `/track/${data.tracking_id}`;
                const h2 = document.querySelector('#booking-step-3 h2');
                if(h2) h2.textContent = "Request Sent!";
                const p = document.querySelector('#booking-step-3 p');
                if(p) p.textContent = "The artist will review your request and get back to you shortly.";
            } else {
                alert(data.detail || "Submission failed");
                document.getElementById('btn-submit-hire').disabled = false;
                document.getElementById('btn-submit-hire').textContent = "Send Request";
            }
        } catch(e) {
            alert("Network error");
        }
    }
"""
        # Inject JS before originalInit
        html = html[:js_start] + js_replacement + "\n" + html[js_start:js_end] + html[js_end:]
        
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

process_template('templates/booking.html', 'templates/booking_session.html', 'session')
process_template('templates/booking.html', 'templates/booking_hire.html', 'hire')
print("Templates generated.")
