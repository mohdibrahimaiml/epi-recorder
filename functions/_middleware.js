/**
 * Optional edge middleware — currently pass-through.
 * API proxying is handled by path-specific functions under functions/api, etc.
 */
export async function onRequest(context) {
  return context.next();
}
