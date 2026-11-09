import { http, HttpResponse, passthrough } from 'msw';
import { MOCK_DB, updateTechLocation } from './db';

export const handlers = [
  // Passthrough for external avatars
  http.get('https://ui-avatars.com/*', () => {
    return passthrough();
  }),

  // Passthrough for Map Tiles (Stadia Maps)
  http.get('https://tiles.stadiamaps.com/*', () => {
    return passthrough();
  }),

  http.post('*/auth/login', async ({ request }) => {
    const { email } = await request.json() as { email: string };
    
    if (email === 'fail@example.com') {
      return new HttpResponse(null, { status: 401 });
    }

    return HttpResponse.json({
      token: 'mock-jwt-token',
      user: {
        id: '1',
        email,
        fullName: 'John Doe',
        role: 'admin',
        status: 'active'
      }
    });
  }),

  http.post('*/auth/register', async ({ request }) => {
    const { email, fullName, companyName } = await request.json() as any;

    if (email === 'exist@example.com') {
      return new HttpResponse(null, { status: 409 });
    }

    return HttpResponse.json({
      token: 'mock-jwt-token',
      user: {
        id: '2',
        email,
        fullName,
        companyName,
        role: 'admin',
        status: 'active'
      }
    });
  }),
  
  http.get('*/auth/me', () => {
    // Check for Authorization header if needed, for simple mock just return user
    return HttpResponse.json({
      id: '1',
      email: 'user@example.com',
      fullName: 'John Doe',
      role: 'admin',
      status: 'active'
    });
  }),

  // Dashboard Stats
  http.get('*/api/v1/dashboard/stats', () => {
    return HttpResponse.json({
        revenue: {
            total: 12450.00,  // pounds (backend divides cents by 100)
            trend: 12.5,
            trendDirection: 'up',
        },
        jobs: {
            today: 12,
            inProgress: 5,
            pending: 2,
        },
        team: {
            active: 8,
            total: 10,
        },
    });
  }),

  // Dashboard Activity Feed
  http.get('*/api/v1/dashboard/activity', () => {
    return HttpResponse.json([
        {
            id: '1',
            type: 'job_completed',
            message: 'Maintenance at Starbucks Downtown completed',
            timestamp: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 mins ago
            priority: 'low',
        },
        {
            id: '2',
            type: 'alert',
            message: 'Technician Mike is 15m late for Job #1023',
            timestamp: new Date(Date.now() - 1000 * 60 * 120).toISOString(), // 2 hours ago
            priority: 'high',
        },
        {
            id: '3',
            type: 'payment',
            message: 'Payment received from Whole Foods ($450.00)',
            timestamp: new Date(Date.now() - 1000 * 60 * 240).toISOString(), // 4 hours ago
            priority: 'medium',
        },
        {
            id: '4',
            type: 'job_created',
            message: 'New job scheduled: HVAC Repair at City Mall',
            timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(), // 5 hours ago
            priority: 'low',
        },
    ]);
  }),
  // Pending jobs sidebar (real backend: GET /api/v1/jobs, schedule.py) — the `*` prefix
  // matches both the short legacy path and the real one, so this serves SchedulePage either way.
  http.get('*/jobs', () => {
    return HttpResponse.json([
       {
         id: 'JOB-101',
         customerName: 'Alice Springs',
         customerPhone: '555-0101',
         address: '123 Maple Ave, Springfield',
         serviceType: 'Plumbing',
         description: 'Leaky faucet in kitchen',
         status: 'pending',
         priority: 'medium',
         scheduledDate: new Date(Date.now() + 86400000).toISOString(), // Tomorrow
         scheduledTime: '09:00',
         price: 150,
         assignedTech: { id: 't1', name: 'Mario', avatar: 'https://ui-avatars.com/api/?name=Mario' }
       },
       {
         id: 'JOB-102',
         customerName: 'Bob Vance',
         customerPhone: '555-0102',
         address: '456 Oak St, Springfield',
         serviceType: 'HVAC',
         description: 'AC maintenance check',
         status: 'completed',
         priority: 'low',
         scheduledDate: new Date(Date.now() - 86400000).toISOString(), // Yesterday
         scheduledTime: '14:30',
         price: 200,
         assignedTech: { id: 't2', name: 'Luigi', avatar: 'https://ui-avatars.com/api/?name=Luigi' }
       },
       {
         id: 'JOB-103',
         customerName: 'Charlie Day',
         customerPhone: '555-0103',
         address: '789 Pine Ln, Springfield',
         serviceType: 'Electrical',
         description: 'Outlet sparking',
         status: 'in_progress',
         priority: 'high',
         scheduledDate: new Date().toISOString(), // Today
         scheduledTime: '11:15',
         price: 0,
         assignedTech: { id: 't3', name: 'Wario', avatar: 'https://ui-avatars.com/api/?name=Wario' }
       }
    ]);
  }),

  // Real API — GET /api/v1/bookings -> BookingReadEnriched[] (snake_case, cents, ISO)
  http.get('*/api/v1/bookings', () => {
    const base = {
      provider_id: 'p1',
      duration_minutes: 60,
      deposit_paid_cents: 0,
      total_paid_cents: 0,
      payment_timing: 'before_service',
      deposit_percentage: 0,
      promo_code: null,
      discount_cents: 0,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json([
      {
        ...base,
        id: 'b-101',
        customer_id: 'c1',
        service_id: 's1',
        field_agent_id: 't1',
        scheduled_time: new Date(Date.now() + 86400000).toISOString(),
        description: 'Leaky faucet in kitchen',
        status: 'confirmed',
        location_postcode: 'M1 1AD',
        location_address: '123 Maple Ave, Springfield',
        base_price_cents: 15000,
        customer_name: 'Alice Springs',
        customer_phone: '555-0101',
        service_name: 'Emergency Plumbing',
        service_type: 'Plumbing',
        assigned_agent_id: 't1',
        assigned_agent_name: 'Mario',
      },
      {
        ...base,
        id: 'b-102',
        customer_id: 'c2',
        service_id: 's2',
        field_agent_id: null,
        scheduled_time: new Date().toISOString(),
        description: 'AC maintenance check',
        status: 'pending',
        location_postcode: 'M2 3WQ',
        location_address: '456 Oak St, Springfield',
        base_price_cents: 20000,
        customer_name: 'Bob Vance',
        customer_phone: '555-0102',
        service_name: 'HVAC Service',
        service_type: 'HVAC',
        assigned_agent_id: null,
        assigned_agent_name: null,
      },
      {
        ...base,
        id: 'b-103',
        customer_id: 'c3',
        service_id: 's3',
        field_agent_id: 't3',
        scheduled_time: new Date(Date.now() - 86400000).toISOString(),
        description: 'Outlet sparking',
        status: 'completed',
        location_postcode: 'M3 5AA',
        location_address: '789 Pine Ln, Springfield',
        base_price_cents: 12000,
        total_paid_cents: 12000,
        customer_name: 'Charlie Day',
        customer_phone: '555-0103',
        service_name: 'Electrical Repair',
        service_type: 'Electrical',
        assigned_agent_id: 't3',
        assigned_agent_name: 'Wario',
      },
    ]);
  }),

  // Real API — POST /api/v1/bookings/ (A2b jobs write)
  http.post('*/api/v1/bookings/', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ id: crypto.randomUUID(), status: 'pending', created_at: new Date().toISOString(), ...body }, { status: 201 });
  }),

  // Real API — GET /api/v1/providers/ (list for job create form)
  http.get('*/api/v1/providers/', () => HttpResponse.json([
    { id: '11111111-1111-1111-1111-111111111111', business_name: 'Swift Plumbing Co' },
    { id: '22222222-2222-2222-2222-222222222222', business_name: 'Bright Electrical Ltd' },
  ])),

  // Real API — POST /api/v1/ai/ingest (C2 KB ingest, admin only)
  http.post('*/api/v1/ai/ingest', async ({ request }) => {
    const body = await request.json() as { documents?: unknown[] };
    const count = Array.isArray(body?.documents) ? body.documents.length : 0;
    return HttpResponse.json({ ingested: count, skipped: 0, message: `Ingested ${count} document(s) into the knowledge base.` }, { status: 200 });
  }),

  // Real API — GET /api/v1/providers/:id/services
  http.get('*/api/v1/providers/:id/services', ({ params }) => {
    const pid = params.id as string;
    if (pid === '11111111-1111-1111-1111-111111111111') {
      return HttpResponse.json([
        { id: 'aaaa0001-0000-0000-0000-000000000000', name: 'Leak Repair', base_price_cents: 8500, duration_minutes: 60 },
        { id: 'aaaa0002-0000-0000-0000-000000000000', name: 'Boiler Service', base_price_cents: 12000, duration_minutes: 90 },
      ]);
    }
    return HttpResponse.json([
      { id: 'bbbb0001-0000-0000-0000-000000000000', name: 'Wiring Inspection', base_price_cents: 9500, duration_minutes: 75 },
    ]);
  }),

  // Real API — POST /api/v1/bookings/guest (B3 no-account booking)
  http.post('*/api/v1/bookings/guest', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json(
      { id: crypto.randomUUID(), status: 'pending', created_at: new Date().toISOString(), ...((body.booking_data as object) ?? {}) },
      { status: 201 }
    );
  }),

  // Real API — POST /api/v1/payments/create-intent
  http.post('*/api/v1/payments/create-intent', async ({ request }) => {
    const body = await request.json() as { booking_id?: string };
    return HttpResponse.json(
      { client_secret: `pi_${crypto.randomUUID().replace(/-/g, '')}_secret_${crypto.randomUUID().replace(/-/g, '')}`, booking_id: body.booking_id ?? null },
      { status: 200 }
    );
  }),

  // Team Members (Read from Shared DB)
  http.get('*/api/v1/team', () => {
    return HttpResponse.json(MOCK_DB.team);
  }),

  // MOBILE: Update Tech Location (The "Heartbeat")
  http.patch('*/api/v1/team/:id/location', async ({ params, request }) => {
    const { id } = params;
    const body = await request.json() as any;

    // Write to our "Shared DB"
    updateTechLocation(id as string, {
      lat: body.lat,
      lng: body.lng,
      heading: body.heading,
      status: body.status || 'busy'
    });

    return HttpResponse.json({ success: true });
  }),

  // Schedule events (real backend: GET /api/v1/schedule, schedule.py) — the `*` prefix
  // matches both the short legacy path and the real one, so this serves SchedulePage either way.
  http.get('*/schedule', () => {
     // Mocking some existing scheduled events
    return HttpResponse.json([
      {
        id: 'JOB-101',
        resourceId: 't1',
        startTime: new Date(new Date().setHours(9, 0, 0, 0)).toISOString(),
        endTime: new Date(new Date().setHours(11, 0, 0, 0)).toISOString(),
        title: 'Leaky faucet',
        status: 'scheduled',
        type: 'Plumbing'
      },
      {
        id: 'JOB-103',
        resourceId: 't3',
        startTime: new Date(new Date().setHours(13, 0, 0, 0)).toISOString(),
        endTime: new Date(new Date().setHours(15, 0, 0, 0)).toISOString(),
        title: 'Outlet sparking',
        status: 'in_progress',
        type: 'Electrical'
      }
    ]);
  }),

  // Real API — POST /api/v1/dispatch/:bookingId/assign/:agentId
  http.post('*/api/v1/dispatch/:bookingId/assign/:agentId', ({ params }) => {
    return HttpResponse.json({ id: params.bookingId, field_agent_id: params.agentId, status: 'assigned' });
  }),

  // LIVE ROUTE GEOMETRY (Mocked as coordinate arrays)
  // Request: GET /api/v1/routes/:techId
  http.get('*/api/v1/routes/:techId', ({ params }) => {
      const { techId } = params;
      
      // Mario path: Buckingham Palace -> Westminster
      if (techId === 't1') {
          return HttpResponse.json({
              techId,
              jobId: 'JOB-101',
              geometry: {
                  type: 'LineString',
                  coordinates: [
                    [-0.1416, 51.5010],
                    [-0.1370, 51.5017],
                    [-0.1320, 51.5027],
                    [-0.1276, 51.5034]
                  ]
              },
              duration: 600, // 10 mins
              distance: 3500,
              status: 'normal'
          });
      }
      
      // Wario path: Clerkenwell -> St Paul's (Delayed)
      if (techId === 't3') {
           return HttpResponse.json({
              techId,
              jobId: 'JOB-103',
              geometry: {
                  type: 'LineString',
                  coordinates: [
                    [-0.0977, 51.5202],
                    [-0.0950, 51.5170],
                    [-0.0983, 51.5138]
                  ]
              },
              duration: 1200, // 20 mins (Delayed)
              distance: 500,
              status: 'delayed'
          });
      }

      return new HttpResponse(null, { status: 404 });
  }),
  // -------------------------------------------------------------
  // CRM: Customers
  // -------------------------------------------------------------
  http.get('*/api/v1/customers', () => {
    return HttpResponse.json([
      {
        id: 'C-101',
        firstName: 'Alice',
        lastName: 'Springs',
        email: 'alice@example.com',
        phone: '555-0101',
        address: { street: '123 Maple Ave', city: 'Springfield', zip: '10001' },
        tags: ['VIP'],
        totalSpend: 4250.00,
        lastServiceDate: new Date(Date.now() - 86400000 * 2).toISOString()
      },
      {
        id: 'C-102',
        firstName: 'Bob',
        lastName: 'Vance',
        email: 'bob@example.com',
        phone: '555-0102',
        address: { street: '456 Oak St', city: 'Springfield', zip: '10002' },
        tags: ['Commercial'],
        totalSpend: 12500.50,
        lastServiceDate: new Date(Date.now() - 86400000 * 10).toISOString()
      },
      {
        id: 'C-103',
        firstName: 'Charlie',
        lastName: 'Day',
        email: 'charlie@example.com',
        phone: '555-0103',
        address: { street: '789 Pine Ln', city: 'Springfield', zip: '10003' },
        tags: ['Late Payment'],
        totalSpend: 150.00,
        lastServiceDate: new Date(Date.now() - 86400000 * 15).toISOString()
      },
      {
        id: 'C-104',
        firstName: 'Diana',
        lastName: 'Prince',
        email: 'diana@example.com',
        phone: '555-0104',
        address: { street: '101 Justice Blvd', city: 'Gotham', zip: '10004' },
        tags: ['VIP', 'Recurring'],
        totalSpend: 8900.00,
        lastServiceDate: new Date(Date.now() - 86400000 * 5).toISOString()
      }
    ]);
  }),

  http.post('*/api/v1/customers', async ({ request }) => {
    const body = await request.json() as any;
    return HttpResponse.json({ id: `C-${Math.floor(Math.random() * 1000)}`, status: 'created', ...body }, { status: 201 });
  }),

  // -------------------------------------------------------------
  // ANALYTICS: Reports
  // -------------------------------------------------------------
  
  // Revenue Trend (Last 30 Days)
  http.get('*/api/v1/reports/revenue', () => {
      const data = [];
      const today = new Date();
      for (let i = 29; i >= 0; i--) {
          const d = new Date(today);
          d.setDate(today.getDate() - i);
          // Random revenue between 500 and 3000, with a slight upward trend
          const base = 500 + (Math.random() * 1000);
          const trend = (30 - i) * 50; 
          data.push({
              date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
              amount: Math.floor(base + trend)
          });
      }
      return HttpResponse.json(data);
  }),

  // Tech Performance
  http.get('*/api/v1/reports/tech-performance', () => {
      return HttpResponse.json([
          { name: 'Mario', completed: 42, delayed: 3 },
          { name: 'Luigi', completed: 38, delayed: 0 },
          { name: 'Wario', completed: 15, delayed: 12 },
          { name: 'Peach', completed: 28, delayed: 1 },
      ]);
  }),

  // Provider Search (B1)
  http.get('*/api/v1/providers/search', () => {
    return HttpResponse.json([
      {
        id: 'prov-1',
        business_name: 'Precision Plumbing Ltd',
        description: 'Expert plumbing and boiler services in London.',
        average_rating: 4.8,
        total_reviews: 123,
        service_radius_km: 30,
        distance_km: 2.4,
        services: [
          { id: 's1', name: 'Boiler Service', service_type: 'Plumbing', base_price_cents: 9900, duration_minutes: 60 },
          { id: 's2', name: 'Leak Repair', service_type: 'Plumbing', base_price_cents: 5500, duration_minutes: 45 },
        ],
      },
      {
        id: 'prov-2',
        business_name: 'SparkRight Electricians',
        description: 'NICEIC certified electricians for residential and commercial work.',
        average_rating: 4.5,
        total_reviews: 87,
        service_radius_km: 25,
        distance_km: 5.1,
        services: [
          { id: 's3', name: 'Rewiring', service_type: 'Electrical', base_price_cents: 45000, duration_minutes: 480 },
        ],
      },
    ]);
  }),

  // Provider Profile (B2)
  http.get('*/api/v1/providers/:providerId', ({ params }) => {
    return HttpResponse.json({
      id: params.providerId,
      business_name: 'Precision Plumbing Ltd',
      description: 'Expert plumbing and boiler services in London.',
      average_rating: 4.8,
      total_reviews: 123,
      service_radius_km: 30,
      distance_km: null,
      services: [
        { id: 's1', name: 'Boiler Service', service_type: 'Plumbing', base_price_cents: 9900, duration_minutes: 60 },
        { id: 's2', name: 'Leak Repair', service_type: 'Plumbing', base_price_cents: 5500, duration_minutes: 45 },
      ],
    });
  }),

  // Reviews list
  http.get('*/api/v1/reviews', () => {
    return HttpResponse.json([
      { id: 'r1', rating: 5, comment: 'Excellent work, very professional.', created_at: new Date().toISOString() },
      { id: 'r2', rating: 4, comment: 'Good job, arrived on time.', created_at: new Date().toISOString() },
    ]);
  }),

  // Post review (B4)
  http.post('*/api/v1/reviews', () => {
    return HttpResponse.json({ id: 'r-new', status: 'created' }, { status: 201 });
  }),
];
