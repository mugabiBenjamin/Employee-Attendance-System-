import { LoginForm } from "./components/login-form";

export default function App() {
  return (
    <>
      <div className="flex justify-center items-center h-[100vh] bg-blue-900/100">
            <LoginForm className="w-[60%]" />
      </div>
    </>
  );
}
