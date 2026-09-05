export const dynamic = "force-dynamic";

export default function Login() {
  return (
    <div className="login">
      <section className="card loginCard">
        <div className="eyebrow">Secure knowledge platform</div>
        <h1>Welcome back</h1>
        <p>Sign in with your organization account. Passwords and SSO are handled by Amazon Cognito.</p>
        <div className="actions" style={{ marginTop: 16 }}>
          <a className="button" href="/auth/login">Continue to sign in</a>
        </div>
      </section>
    </div>
  );
}
