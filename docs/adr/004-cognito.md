# ADR 004: Amazon Cognito for User Authentication

## Status
Accepted for secure application phase.

## Decision
Use Amazon Cognito as the identity provider and validate JWTs in the backend using issuer/JWKS metadata.

## Non-goal
The application will not implement password storage/authentication from scratch.

## Phase 0/1 consequence
Identity is documentation-only and the local CLI is a trusted developer tool.
