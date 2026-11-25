import { defineRailway, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "dispute-shield";
export default defineRailway(() => {
  const uploads = volume("dispute-shield-volume", { sizeMB: 500, region: "sfo" });
  const disputeShield = service("dispute-shield", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE" },
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: { "sfo": 1 },
    volumeMounts: { "/data": uploads },
  });

  return project("dispute-shield", {
    variables: { managed: false },
    resources: [disputeShield, uploads],
  });
});
