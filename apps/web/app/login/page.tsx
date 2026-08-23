"use client";

export default function Login() {
  const login = () => {
    const base = process.env.NEXT_PUBLIC_COGNITO_AUTHORIZE_URL!;
    const client = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!;
    const redirect = `${process.env.NEXT_PUBLIC_APP_URL}/auth/callback`;
    window.location.href = `${base}?client_id=${encodeURIComponent(client)}&response_type=code&scope=openid+email+profile&redirect_uri=${encodeURIComponent(redirect)}`;
  };
  return <div className="login"><section className="card loginCard"><div className="eyebrow">Secure knowledge platform</div><h1>Welcome back</h1><p>Sign in with your organization account. Passwords and SSO are handled by Amazon Cognito.</p><label>Email</label><input type="email" placeholder="you@company.com" autoComplete="email" /><div className="actions" style={{marginTop:16}}><button onClick={login}>Continue to sign in</button><button className="secondary" onClick={login}>Use SSO</button></div><p><a href="#" onClick={(e)=>{e.preventDefault();login();}}>Forgot password?</a></p></section></div>;
}
