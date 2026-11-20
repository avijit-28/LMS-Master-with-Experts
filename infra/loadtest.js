import http from 'k6/http';
import { check, sleep, group } from 'k6';

// ==============================================================================
// EduPlatform LMS: Production k6 Automated Load Testing Suite
// Evaluates p95 latency, error rates, and concurrent capacity across 10 -> 100 VUs.
// ==============================================================================

export const options = {
  stages: [
    { duration: '30s', target: 10 },  // Stage 1: Warmup & baseline (10 users)
    { duration: '1m',  target: 25 },  // Stage 2: Normal classroom load (25 users)
    { duration: '1m',  target: 50 },  // Stage 3: Peak exam submission load (50 users)
    { duration: '30s', target: 100 }, // Stage 4: Stress limit test (100 users)
    { duration: '30s', target: 0 },   // Stage 5: Graceful cooldown
  ],
  thresholds: {
    // 95% of web requests must complete under 600ms
    http_req_duration: ['p(95)<600', 'p(99)<1500'],
    // HTTP error rate must remain below 1%
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:56102';

export default function () {
  // ----------------------------------------------------------------------------
  // Scenario 1: Course Catalog Browsing (Read-Heavy / MVC Action)
  // ----------------------------------------------------------------------------
  group('01_Catalog_Browsing', function () {
    const resCatalog = http.get(`${BASE_URL}/Courses`);
    check(resCatalog, {
      'catalog status is 200': (r) => r.status === 200,
      'catalog response under 600ms': (r) => r.timings.duration < 600,
    });
  });

  sleep(1);

  // ----------------------------------------------------------------------------
  // Scenario 2: Active Course & Syllabus Details View (EF6 Query Execution)
  // ----------------------------------------------------------------------------
  group('02_Course_Details_View', function () {
    const resDetails = http.get(`${BASE_URL}/Courses/Details/1`);
    check(resDetails, {
      'course details status is 200 or 404': (r) => r.status === 200 || r.status === 404,
      'details response under 800ms': (r) => r.timings.duration < 800,
    });
  });

  sleep(1.5);

  // ----------------------------------------------------------------------------
  // Scenario 3: AI Assistant Consultation (Semantic Cache & Microservice)
  // ----------------------------------------------------------------------------
  group('03_AI_Assistant_Interaction', function () {
    const chatPayload = JSON.stringify({
      Message: 'What is the syllabus and grading policy for this course?',
      CourseId: 1,
      LearningMode: 'CourseAssistant'
    });

    const chatParams = {
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
    };

    const resChat = http.post(`${BASE_URL}/ChatBot/SendMessage`, chatPayload, chatParams);
    check(resChat, {
      'chat status 200 or 429 rate-limited': (r) => r.status === 200 || r.status === 429,
    });
  });

  sleep(2);

  // ----------------------------------------------------------------------------
  // Scenario 4: Real-Time SSE Token Stream (Anti-Buffering Verification)
  // ----------------------------------------------------------------------------
  group('04_SSE_Streaming_Endpoint', function () {
    const streamUrl = `${BASE_URL}/ChatBotStream/StreamMessage?prompt=Hello&courseId=1`;
    const resStream = http.get(streamUrl);
    check(resStream, {
      'stream status 200': (r) => r.status === 200,
      'stream has x-accel-buffering no': (r) => r.headers['X-Accel-Buffering'] === 'no' || r.headers['x-accel-buffering'] === 'no',
    });
  });

  sleep(2);
}
