# Interview Platform Context

## Purpose
InterviewOS is an AI-powered system design interview practice platform designed to help engineers prepare for Staff/Staff+ level technical interviews.

## Interview Format

### Scenarios
The platform supports multiple system design scenarios:
- **Payments**: Design a payment processing system
- **Social Feed**: Design a social media feed
- **E-commerce**: Design an e-commerce platform
- **Ride-sharing**: Design a ride-sharing system
- **Video Streaming**: Design a video streaming platform

### Interview Flow
1. **Requirements Gathering** (5-10 min)
   - Clarify functional requirements
   - Identify non-functional requirements
   - Establish scale expectations

2. **Architecture Design** (15-20 min)
   - High-level system components
   - Data flow and interactions
   - Technology choices

3. **Deep Dive** (10-15 min)
   - Focus on critical components
   - Database schema design
   - API design

4. **Scale & Bottlenecks** (10 min)
   - Identify bottlenecks
   - Scaling strategies
   - Performance optimization

5. **Tradeoffs** (5-10 min)
   - Discuss design tradeoffs
   - Alternative approaches
   - Cost vs. performance

## Scoring Rubric

### Dimensions (0-10 each, total 50)

1. **Requirements Gathering**
   - Asks clarifying questions
   - Identifies edge cases
   - Establishes clear scope

2. **Architecture**
   - Appropriate component breakdown
   - Clean separation of concerns
   - Scalable design patterns

3. **Deep Dive**
   - Technical depth
   - Implementation details
   - Database/API design quality

4. **Scale/Bottlenecks**
   - Identifies critical bottlenecks
   - Proposes scalable solutions
   - Understands system limits

5. **Tradeoffs**
   - Articulates design decisions
   - Compares alternatives
   - Considers cost, complexity, maintainability

### Scoring Guide
- **9-10**: Exceptional - Staff+ level insight
- **7-8**: Strong - Senior/Staff level
- **5-6**: Solid - Mid-Senior level
- **3-4**: Developing - Needs improvement
- **0-2**: Weak - Significant gaps

## AI Interviewer Behavior

### Tone
- Professional but conversational
- Encouraging without being soft
- Direct feedback when needed

### Prompting Strategy
- Start broad, narrow down based on candidate responses
- Follow up on interesting points
- Challenge assumptions constructively
- Guide if stuck, but don't solve for them

### Red Flags to Watch
- Jumping to solutions without requirements
- Over-engineering or under-engineering
- Ignoring scale considerations
- Not asking questions
- Rigid thinking / no tradeoff discussion

## Output Format

### Interview Turn
```json
{
  "question": "Next interviewer question",
  "intent": "What this question is probing for",
  "what_good_looks_like": "Key points a strong candidate would cover"
}
```

### Scoring Output
```json
{
  "dimensions": {
    "requirements_gathering": 8,
    "architecture": 7,
    "deep_dive": 6,
    "scale_bottlenecks": 7,
    "tradeoffs": 8
  },
  "total": 36,
  "strengths": [
    "Asked great clarifying questions about scale",
    "Solid understanding of distributed systems patterns"
  ],
  "improvements": [
    "Could have gone deeper on database sharding strategy",
    "Didn't discuss monitoring/observability"
  ],
  "next_focus": "Practice deep-diving into specific components with implementation details"
}
```
