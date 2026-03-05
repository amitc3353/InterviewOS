/**
 * Static scenario data for the landing page.
 * Mirrors scenario metadata from backend/scenarios/*.yaml.
 * Used as a fallback when GET /api/scenarios is unavailable.
 */

import type { Scenario } from "./types";

export const STATIC_SCENARIOS: Scenario[] = [
  {
    id: "url-shortener",
    name: "Design a URL Shortener",
    description:
      "Design a URL shortening service like bit.ly. Handle short code generation, redirect lookups, and click analytics at scale.",
    archetype: "crud-metadata",
    difficulty: "easy",
  },
  {
    id: "rate-limiter",
    name: "Design a Rate Limiter",
    description:
      "Build a distributed rate limiting service. Handle sliding windows, token buckets, and multi-tier rate limiting across a fleet.",
    archetype: "crud-metadata",
    difficulty: "easy",
  },
  {
    id: "typeahead-autocomplete",
    name: "Design Typeahead Autocomplete",
    description:
      "Build a real-time autocomplete system. Handle prefix matching, ranking, and sub-100ms latency at scale.",
    archetype: "crud-metadata",
    difficulty: "easy",
  },
  {
    id: "real-time-chat",
    name: "Design Real-Time Chat",
    description:
      "Design a messaging platform like Slack. Handle real-time delivery, presence, read receipts, and message persistence.",
    archetype: "feed-timeline",
    difficulty: "medium",
  },
  {
    id: "notification-system",
    name: "Design a Notification System",
    description:
      "Build a multi-channel notification service. Handle push, email, SMS delivery with rate limiting and user preferences.",
    archetype: "real-time-streaming",
    difficulty: "medium",
  },
  {
    id: "news-feed",
    name: "Design a News Feed",
    description:
      "Design a social media news feed like Twitter or Facebook. Handle fan-out, ranking, and real-time updates.",
    archetype: "feed-timeline",
    difficulty: "medium",
  },
  {
    id: "file-storage",
    name: "Design a File Storage Service",
    description:
      "Build a cloud file storage system like Dropbox. Handle uploads, chunking, deduplication, and sync across devices.",
    archetype: "platform-infra",
    difficulty: "medium",
  },
  {
    id: "video-streaming",
    name: "Design a Video Streaming Service",
    description:
      "Design a video streaming platform. Handle transcoding, adaptive bitrate, CDN distribution, and live streaming.",
    archetype: "real-time-streaming",
    difficulty: "medium",
  },
  {
    id: "payment-gateway",
    name: "Design a Payment Gateway",
    description:
      "Build a payment processing system. Handle transactions, idempotency, reconciliation, and PCI compliance.",
    archetype: "transactional",
    difficulty: "hard",
  },
  {
    id: "distributed-cache",
    name: "Design a Distributed Cache",
    description:
      "Design a distributed caching layer like Memcached or Redis. Handle partitioning, replication, eviction, and consistency.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
  {
    id: "recommendation-engine",
    name: "Design a Recommendation Engine",
    description:
      "Build a recommendation system for e-commerce or content. Handle collaborative filtering, real-time signals, and cold start.",
    archetype: "ml-system",
    difficulty: "hard",
  },
  {
    id: "ride-sharing",
    name: "Design a Ride-Sharing Platform",
    description:
      "Design a ride-sharing system like Uber. Handle matching, geospatial queries, surge pricing, and real-time tracking.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
  {
    id: "distributed-task-scheduler",
    name: "Design a Distributed Task Scheduler",
    description:
      "Build a distributed job scheduling system. Handle task queuing, priority, retries, and exactly-once execution.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
  {
    id: "ecommerce-inventory",
    name: "Design E-Commerce Inventory",
    description:
      "Build an inventory management system. Handle stock tracking, reservations, consistency across warehouses, and flash sales.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
  {
    id: "metrics-monitoring",
    name: "Design a Metrics & Monitoring System",
    description:
      "Design a time-series metrics platform like Datadog. Handle ingestion, aggregation, alerting, and dashboards at scale.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
  {
    id: "video-streaming-platform",
    name: "Design a Video Streaming Platform",
    description:
      "Design a full video platform like YouTube. Handle upload processing, recommendation, content delivery, and creator tools.",
    archetype: "platform-infra",
    difficulty: "hard",
  },
];
