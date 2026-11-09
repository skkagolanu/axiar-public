import { Outlet } from 'react-router-dom';

export default function AuthLayout() {
  return (
    <div className="flex min-h-screen w-full">
      {/* Left Side: Brand (Hidden on mobile) */}
      <div className="hidden lg:flex w-1/2 flex-col items-center justify-center bg-secondary p-10 text-white relative">
        <div className="flex items-center gap-4 mb-8">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 font-heading text-5xl font-bold text-white">
            A
          </div>
          <span className="font-heading text-6xl font-bold tracking-tighter text-white">Axiar</span>
        </div>
        
        <div className="max-w-md text-center">
          <h1 className="font-heading text-4xl font-bold leading-tight text-white">
            Empowering Service Teams.
          </h1>
          <p className="mt-4 text-slate-300">
            The AI-first operating system for the next generation of service businesses.
          </p>
        </div>

        <div className="absolute bottom-10 text-sm text-slate-400">
          &copy; {new Date().getFullYear()} Axiar Co.
        </div>
      </div>

      {/* Right Side: Form */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-background p-8">
        <div className="w-full max-w-sm">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
