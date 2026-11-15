// Cloudflare Pages Function: GET /api/votes
// Restituisce tutti i voti. Protetta da token (header Authorization: Bearer <FEEDBACK_TOKEN>).
export async function onRequestGet({ request, env }) {
  const auth = request.headers.get("Authorization") || "";
  if (!env.FEEDBACK_TOKEN || auth !== `Bearer ${env.FEEDBACK_TOKEN}`) {
    return new Response("Non autorizzato", { status: 401 });
  }
  const votes = [];
  let cursor;
  do {
    const page = await env.VOTES.list({ prefix: "v:", cursor });
    for (const k of page.keys) {
      const value = await env.VOTES.get(k.name);
      if (value) votes.push(JSON.parse(value));
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return Response.json(votes);
}
